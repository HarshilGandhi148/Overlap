"""Typesense owns eligibility and semantic retrieval; Python aggregates scores."""
import math
import re
import time
import typesense
from core.services import Settings
from nearby.models import AppError, RecommendationResponse, MAX_PLACES
from nearby.ranking import rank

PAGE_SIZE=250
MODEL='ts/all-MiniLM-L12-v2'


def schema(name):
    fields=[{'name':n,'type':t} for n,t in [
        ('name','string'),('description','string'),('search_text','string'),('location','geopoint'),
        ('categories','string[]'),('has_cost','bool'),('has_duration','bool'),('wheelchair','string'),
        ('fetched_at','int64')]]
    for f in fields:
        if f['name'] in ('categories','wheelchair','has_cost','has_duration'): f['facet']=True
    fields += [{'name':n,'type':t,'optional':True} for n,t in [('cost_min','float'),('cost_max','float'),('duration_min','int32'),('duration_max','int32')]]
    fields.append({'name':'embedding','type':'float[]','embed':{'from':['search_text'],'model_config':{'model_name':MODEL}}})
    return {'name':name,'fields':fields}


def client_from_settings(settings):
    if not settings.api_key: raise AppError('Configure .env and start Typesense. See the setup instructions in README.md.')
    return typesense.Client({'nodes':[{'host':settings.host,'port':settings.port,'protocol':settings.protocol}],
        'api_key':settings.api_key,'connection_timeout_seconds':120,'num_retries':0})


def id_filter(ids):
    if not ids or len(ids)>MAX_PLACES or any(not re.fullmatch(r'[A-Za-z0-9_:-]+',i) for i in ids):
        raise ValueError('The active area must contain 1–1,000 valid place identifiers.')
    return 'id:=['+','.join(f'`{i}`' for i in ids)+']'


def geo_filter(outing,ids):
    loc=outing.location
    return f'{id_filter(ids)} && location:({loc.latitude},{loc.longitude},{outing.radius_miles} mi)'


def hard_filter(outing,ids):
    clauses=[geo_filter(outing,ids)]
    if outing.enforce_metadata_limits:
        clauses += ['has_cost:=true','has_duration:=true', f'cost_max:<={outing.budget_limit}',f'duration_max:<={outing.time_limit}']
    if outing.exclusions: clauses.append('categories:!=['+','.join(outing.exclusions)+']')
    if outing.enforce_metadata_limits and any(p.wheelchair for p in outing.people): clauses.append('wheelchair:=yes')
    return ' && '.join(clauses)


class SearchService:
    def __init__(self,settings=None,client=None,collection=None):
        self.settings=settings or Settings.from_env()
        self.client=client or client_from_settings(self.settings)
        self.collection=collection or f'{self.settings.prefix}_nearby_v1'

    def ensure_collection(self):
        try:
            actual=self.client.collections[self.collection].retrieve()
            expected={f['name']:f for f in schema(self.collection)['fields']}
            present={f['name']:f for f in actual['fields']}
            if any(n not in present or present[n]['type']!=f['type'] for n,f in expected.items()):
                raise AppError('The nearby collection has an incompatible schema. Use a new TYPESENSE_COLLECTION_PREFIX.')
        except typesense.exceptions.ObjectNotFound:
            try: self.client.collections.create(schema(self.collection))
            except typesense.exceptions.ObjectAlreadyExists: pass

    def index_places(self,places):
        if not places: return [],0
        try:
            self.ensure_collection()
            successful=[];failed=0
            for start in range(0,len(places),100):
                batch=places[start:start+100]
                response=self.client.collections[self.collection].documents.import_([a.document() for a in batch],{'action':'upsert'})
                if isinstance(response,str): response=[__import__('json').loads(s) for s in response.splitlines()]
                if len(response)!=len(batch): raise AppError('Typesense returned an incomplete indexing response. Retry loading the area.')
                for activity,item in zip(batch,response):
                    if item.get('success'): successful.append(activity.id)
                    else: failed+=1
            return successful,failed
        except AppError: raise
        except Exception as exc:
            raise AppError('Typesense could not index the area. Check the search server and its model download, then retry.') from exc

    def _multi(self,queries):
        response=self.client.multi_search.perform({'searches':queries},{})
        results=response.get('results',[])
        if len(results)!=len(queries) or any('error' in r or 'found' not in r for r in results):
            raise AppError('Typesense could not complete every search. Check the server and retry; no partial group ranking was used.')
        return results

    def recommend(self,outing,candidate_ids):
        start=time.perf_counter()
        if not candidate_ids: return RecommendationResponse([],[],0,0,0,0,0)
        try:
            base={'collection':self.collection,'q':'*','per_page':0}
            geographic=geo_filter(outing,candidate_ids)
            filtered=hard_filter(outing,candidate_ids)
            loc=outing.location
            nearest_base={'collection':self.collection,'q':'*','filter_by':filtered,
                'sort_by':f'location({loc.latitude},{loc.longitude}):asc',
                'exclude_fields':'embedding','per_page':PAGE_SIZE}
            diagnostic=self._multi([
                {**base,'filter_by':geographic},
                {**base,'filter_by':geographic+' && (has_cost:=false || has_duration:=false)'},
                {**nearest_base,'page':1},
            ])
            eligible=int(diagnostic[2]['found'])
            nearest_ids=[h['document']['id'] for h in diagnostic[2].get('hits',[])]
            if eligible==0:
                return RecommendationResponse([],[],0,diagnostic[0]['found'],diagnostic[1]['found'],time.perf_counter()-start,len(candidate_ids))
            nearest_pages=[{**nearest_base,'page':p} for p in range(2,math.ceil(eligible/PAGE_SIZE)+1)]
            if nearest_pages:
                for r in self._multi(nearest_pages): nearest_ids.extend(h['document']['id'] for h in r['hits'])
            # Full retrieval protects compromise candidates from top-k truncation.
            # k covers the batch, and the cutoff forces exact search for this bounded index.
            queries=[];owners=[]
            for person in outing.people:
                for page in range(1,math.ceil(eligible/PAGE_SIZE)+1):
                    queries.append({'collection':self.collection,'q':person.opinion.strip(),'query_by':'embedding',
                        'filter_by':filtered,'vector_query':f'embedding:([], k:{len(candidate_ids)}, flat_search_cutoff:{MAX_PLACES+1})',
                        'exclude_fields':'embedding','per_page':PAGE_SIZE,'page':page})
                    owners.append(person.id)
            documents={};distances={p.id:{} for p in outing.people}
            for owner,response in zip(owners,self._multi(queries)):
                if response['found']!=eligible:
                    raise AppError('The activity index changed during the search. Retry to get a consistent group ranking.')
                for hit in response.get('hits',[]):
                    doc=hit['document'];ident=doc['id'];distance=hit.get('vector_distance')
                    if distance is None or not math.isfinite(distance):
                        raise AppError('A semantic score was missing. Retry the search; incomplete matches were not ranked.')
                    documents[ident]=doc;distances[owner][ident]=distance
            expected=set(nearest_ids)
            if len(expected)!=eligible or any(set(scores)!=expected for scores in distances.values()):
                raise AppError('Typesense did not score every activity for every person. Retry the complete search.')
            ranked=rank(outing,documents,distances)
            mapping={r.document['id']:r for r in ranked}
            return RecommendationResponse(ranked,[mapping[i] for i in nearest_ids],eligible,diagnostic[0]['found'],diagnostic[1]['found'],time.perf_counter()-start,len(candidate_ids))
        except AppError: raise
        except Exception as exc:
            raise AppError('Typesense search is unavailable. Check the server and retry. Your inputs have been kept.') from exc

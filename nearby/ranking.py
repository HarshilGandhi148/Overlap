from nearby.models import RankedActivity, distance_miles

WEIGHTS={'opinions':.70,'distance':.15,'time':.10,'cost':.05}

def clamp(value): return max(0.0,min(1.0,value))

def rank(outing, documents, distances):
    result=[]
    for ident,doc in documents.items():
        scores={p.id:clamp(1-distances[p.id][ident]/2) for p in outing.people}
        values=list(scores.values())
        miles=distance_miles(outing.location.key,doc['location'])
        components={
            'opinions':.6*min(values)+.4*sum(values)/len(values),
            'distance':clamp(1-miles/outing.radius_miles),
            'time':clamp(1-doc['duration_max']/outing.time_limit) if outing.enforce_metadata_limits else 0,
            'cost':(clamp(1-doc['cost_max']/outing.budget_limit) if outing.budget_limit else 1.0) if outing.enforce_metadata_limits else 0,
        }
        result.append(RankedActivity(doc,100*sum((WEIGHTS if outing.enforce_metadata_limits else {'opinions':.85,'distance':.15,'time':0,'cost':0})[k]*v for k,v in components.items()),miles,scores,components))
    return sorted(result,key=lambda r:(-r.score,r.distance_miles,r.document['id']))

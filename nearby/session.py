"""Pure helpers for location and input invalidation."""
from dataclasses import dataclass
from nearby.models import AreaBatch, OutingRequest, RecommendationResponse

@dataclass
class OutingSession:
    location_token: tuple | None = None
    area: AreaBatch | None = None
    request: OutingRequest | None = None
    response: RecommendationResponse | None = None
    selected_id: str | None = None

    def invalidate_results(self):
        self.request=None;self.response=None;self.selected_id=None

    def change_location(self,location,mode=None):
        token=(mode or location.mode,*location.key)
        if token!=self.location_token:
            self.location_token=token;self.area=None;self.invalidate_results()

    def change_request(self,request):
        if self.request is not None and self.request!=request: self.invalidate_results()

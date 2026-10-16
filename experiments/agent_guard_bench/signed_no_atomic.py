"""Real signed delegation baseline; only research budget atomicity is absent."""

from .research_contracts import ResearchPoPContext
from .research_service import ResearchService


class SignedNoAtomic:
    mode = "noAtomic"
    possession = "VERIFIED"
    receipt = "NOT_APPLICABLE"
    independent_audit = "NOT_APPLICABLE"

    def __init__(self, service):
        if type(service) is not ResearchService or service.store.mode != self.mode:
            raise ValueError("frozen genuine noAtomic research service required")
        self.service = service

    @property
    def store(self):
        return self.service.store

    def authenticate(self, **request):
        return self.service.authenticate(**request)

    def initialize_path(self, context):
        return self.service.initialize_path(context)

    def accept(self, context, *, controlled_before_update=None):
        if type(context) is not ResearchPoPContext:
            raise ValueError("genuine verified research PoP context required")
        return self.service.accept(context, controlled_before_update=controlled_before_update)

    def invoke(self, **request):
        return self.accept(self.authenticate(**request))

    def authenticate_query(self, **request):
        return self.service.authenticate_query(**request)

    def query(self, context):
        return self.service.query(context)

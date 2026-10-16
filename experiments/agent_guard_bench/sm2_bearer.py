"""Genuine SM2 Bearer baseline: possession is absent, current authority retained."""

from .research_contracts import BearerContext
from .research_service import ResearchService


class SM2Bearer:
    mode = "Bearer"
    possession = "NOT_VERIFIED"
    supplied_proof = "IGNORED"
    receipt = "NOT_APPLICABLE"
    independent_audit = "NOT_APPLICABLE"
    replay = "NOT_APPLICABLE"

    def __init__(self, service):
        if type(service) is not ResearchService or service.store.mode != self.mode:
            raise ValueError("frozen genuine Bearer research service required")
        self.service = service

    @property
    def store(self):
        return self.service.store

    def authenticate(self, **request):
        context = self.service.authenticate(**request)
        if type(context) is not BearerContext or context.proof is not None:
            raise ValueError("strict absent-possession Bearer context required")
        return context

    def initialize_path(self, context):
        return self.service.initialize_path(context)

    def accept(self, context):
        if type(context) is not BearerContext or context.proof is not None:
            raise ValueError("strict absent-possession Bearer context required")
        return self.service.accept(context)

    def invoke(self, **request):
        return self.accept(self.authenticate(**request))

    def authenticate_query(self, **request):
        return self.service.authenticate_query(**request)

    def query(self, context):
        return self.service.query(context)

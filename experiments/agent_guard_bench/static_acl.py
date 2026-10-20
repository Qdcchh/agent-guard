"""Approved password ACL baseline; credentials and policies come from the owner."""

from .research_contracts import ACLContext
from .research_service import ResearchService


class StaticACL:
    mode = "staticACL"
    possession = "PASSWORD_AUTHENTICATED"
    budget = "NOT_ENFORCED_RESEARCH_ONLY"
    receipt = "NOT_APPLICABLE"
    independent_audit = "NOT_APPLICABLE"
    replay = "NOT_APPLICABLE"

    def __init__(self, service):
        if type(service) is not ResearchService or service.store.mode != self.mode:
            raise ValueError("frozen approved password ACL research service required")
        self.service = service

    @property
    def store(self):
        return self.service.store

    def authenticate(self, **request):
        return self.service.authenticate(**request)

    def initialize_path(self, context):
        return self.service.initialize_path(context)

    def accept(self, context):
        if type(context) is not ACLContext:
            raise ValueError("approved password ACL context required")
        return self.service.accept(context)

    def invoke(self, **request):
        return self.accept(self.authenticate(**request))

    def authenticate_query(self, **request):
        return self.service.authenticate_query(**request)

    def query(self, context):
        return self.service.query(context)

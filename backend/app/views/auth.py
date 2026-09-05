"""Auth view: registration."""
# DECISION: RegisterView uses AllowAny (public endpoint) with a strict throttle_scope ("register") rather than IsAuthenticated. This aligns with DPDP consent capture at registration time — every user must be able to create an account, but account-creation spam is rate-limited per IP. Tradeoff: open endpoint requires robust validation in RegisterSerializer (consent + copyright acknowledgment) rather than relying on auth boundary.
from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework.permissions import AllowAny

from ..serializers import RegisterSerializer

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    # Everyone must be able to hit this endpoint to sign up!
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer
    # SECURITY: 5 registrations/hour/IP (scoped to 'register'). Default
    # AnonRateThrottle is 100/hour — too loose for account-creation spam.
    throttle_scope = 'register'

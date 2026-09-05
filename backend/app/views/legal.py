"""Legal / compliance endpoints for DPDP readiness (ISSUE-03)."""
from rest_framework import generics, permissions, throttling
from rest_framework.response import Response
from django.conf import settings


class ComplianceContactView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [throttling.ScopedRateThrottle]
    throttle_scope = 'legal'

    def get(self, request, *args, **kwargs):
        # ISSUE-03: Return compliance / grievance / nodal officer info.
        # DECISION: Read from settings/env rather than DB table for
        # simplicity (single source of truth, easy to rotate without migration).
        # Tradeoff: Requires deploy to update vs. admin-editable DB row.
        return Response({
            'compliance_officer': {
                'name': getattr(settings, 'COMPLIANCE_OFFICER_NAME', 'Not configured'),
                'email': getattr(settings, 'COMPLIANCE_OFFICER_EMAIL', ''),
            },
            'grievance_officer': {
                'name': getattr(settings, 'GRIEVANCE_OFFICER_NAME', 'Not configured'),
                'email': getattr(settings, 'GRIEVANCE_OFFICER_EMAIL', ''),
            },
            'nodal_contact': {
                'name': getattr(settings, 'NODAL_CONTACT_NAME', 'Not configured'),
                'email': getattr(settings, 'NODAL_CONTACT_EMAIL', ''),
            },
        })

from rest_framework import status
from ..models import TakedownRequest, AudioClip

class TakedownRequestView(generics.GenericAPIView):
    """POST /legal/takedown/ endpoint for copyright owner-facing takedown.

    ISSUE-05: Uses TakedownRequest model (Agent 1 added) linked to AudioClip.
    DECISION: Minimal v1 endpoint — accepts reason, requester_email, clip_id.
    A production system should include counter-notice support, verification,
    and automated acknowledgment timelines.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [throttling.ScopedRateThrottle]
    throttle_scope = 'legal'

    def post(self, request, *args, **kwargs):
        clip_id = request.data.get('clip_id')
        reason = request.data.get('reason', '')
        requester_email = request.data.get('requester_email', '')
        if not clip_id or not reason:
            return Response({"error": "clip_id and reason are required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            clip = AudioClip.objects.get(id=clip_id)
        except AudioClip.DoesNotExist:
            return Response({"error": "Clip not found."}, status=status.HTTP_404_NOT_FOUND)
        TakedownRequest.objects.create(
            clip=clip,
            reason=reason,
            requester_email=requester_email,
            status='pending',
        )
        return Response({
            "status": "received",
            "message": "Takedown request recorded. You will receive acknowledgment within 24 hours.",
            "clip_id": str(clip.id),
        }, status=status.HTTP_201_CREATED)

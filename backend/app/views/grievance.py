"""Grievance endpoint for ISSUE-03 (DPDP grievance / compliance)."""
from rest_framework import generics, permissions, status, throttling
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from ..models import Grievance  # will import from models


class GrievanceCreateView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [throttling.ScopedRateThrottle]
    throttle_scope = 'grievance'

    def get_queryset(self):
        return Grievance.objects.all()

    def create(self, request, *args, **kwargs):
        # ISSUE-03: Accept grievance and create DB row; automated 24h acknowledgment.
        data = request.data.copy()
        data['status'] = 'received'
        # Set acknowledgment due to 24h from now
        acknowledgment_due = timezone.now() + timedelta(hours=24)
        data['acknowledgment_due'] = acknowledgment_due
        serializer_class = None  # We'll handle manually for simplicity
        # HACK: Direct model creation to avoid extra serializer file.
        user = request.user if request.user.is_authenticated else None
        grievance = Grievance.objects.create(
            subject=data.get('subject', ''),
            description=data.get('description', ''),
            user=user,
            user_email=data.get('user_email') or (user.email if user else None),
            status='received',
            acknowledgment_due=acknowledgment_due,
        )
        return Response({
            'grievance_id': grievance.id,
            'status': grievance.status,
            'acknowledgment_due': acknowledgment_due,
            'message': 'Grievance received. Acknowledgment within 24 hours.',
        }, status=status.HTTP_201_CREATED)

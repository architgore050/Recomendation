"""Logging filter that injects correlation_id + audit identity into every log record."""
import logging
import contextvars

from .correlation import get_correlation_id

_audit_user_id = contextvars.ContextVar('audit_user_id', default=None)
_audit_client_ip = contextvars.ContextVar('audit_client_ip', default=None)
_audit_endpoint = contextvars.ContextVar('audit_endpoint', default=None)


def set_audit_identity(user_id, client_ip, endpoint_path):
    _audit_user_id.set(user_id)
    _audit_client_ip.set(client_ip)
    _audit_endpoint.set(endpoint_path)


def clear_audit_identity():
    _audit_user_id.set(None)
    _audit_client_ip.set(None)
    _audit_endpoint.set(None)


class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = get_correlation_id() or '-'
        record.user_id = _audit_user_id.get() or '-'
        record.client_ip = _audit_client_ip.get() or '-'
        record.endpoint_path = _audit_endpoint.get() or '-'
        return True

from celery import shared_task
from .models import SystemMetric

@shared_task
def create_system_metrics_task(metrics_list):
    """
    Bulk create system metrics to avoid blocking request threads.
    Expected format: list of dicts with keys: metric_type, metric_name, value, unit.
    """
    if not metrics_list:
        return
    
    metrics_to_create = [
        SystemMetric(
            metric_type=m.get('metric_type'),
            metric_name=m.get('metric_name'),
            value=m.get('value'),
            unit=m.get('unit', '')
        )
        for m in metrics_list
    ]
    
    SystemMetric.objects.bulk_create(metrics_to_create)

from django.urls import path
from . import views

urlpatterns = [
    path('plans/',                               views.PlanListView.as_view(),              name='subscription_plans'),
    path('details/<uuid:organization_id>/',      views.SubscriptionDetailView.as_view(),    name='subscription_details'),
    path('initiate/<uuid:organization_id>/',     views.InitiateSubscriptionView.as_view(),  name='initiate_subscription'),
    path('verify/',                              views.verify_payment,                      name='verify_payment'),
    path('webhook/paystack/',                    views.PaystackWebhookView.as_view(),       name='paystack_webhook'),
    path('webhook/flutterwave/',                 views.FlutterwaveWebhookView.as_view(),    name='flutterwave_webhook'),
    path('cancel/<uuid:organization_id>/',       views.CancelSubscriptionView.as_view(),    name='cancel_subscription'),
    path('downgrade/<uuid:organization_id>/',    views.DowngradeSubscriptionView.as_view(), name='downgrade_subscription'),
    # Coupon & pricing calculator (public — no auth required)
    path('coupon/validate/',                     views.validate_coupon,                     name='validate_coupon'),
    path('calculator/',                          views.calculate_custom_price,              name='custom_pricing_calculator'),
]

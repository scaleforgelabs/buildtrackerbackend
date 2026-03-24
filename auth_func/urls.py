from django.urls import path
from .views import profile, social_auth, auth_new

urlpatterns = [
    path('register/', auth_new.register_view, name='register'),
    path('register/invitation/', auth_new.register_with_invitation_view, name='register_with_invitation'),
    path('register/workspace-invitation/', auth_new.register_with_workspace_invitation_view, name='register_with_workspace_invitation'),
    path('login/', auth_new.login_view, name='login'),
    path('logout/', auth_new.logout_view, name='logout'),
    path('refresh-token/', auth_new.refresh_token_view, name='refresh_token'),
    path('forgot-password/', auth_new.forgot_password_view, name='forgot_password'),
    path('reset-password/', auth_new.reset_password_view, name='reset_password'),
    path('me/', auth_new.me_view, name='me'),
    path('profile/', profile.user_profile, name='update_profile'),
    path('change-password/', profile.change_password_view, name='change_password'),
    path('create-organization/', auth_new.create_organization_view, name='create_organization'),
    path('verify-otp/', auth_new.verify_otp_view, name='verify_otp'),
    path('resend-otp/', auth_new.resend_otp_view, name='resend_otp'),
    
    path('google/', social_auth.google_auth, name='google_auth'),
    path('apple/', social_auth.apple_auth, name='apple_auth'),
]

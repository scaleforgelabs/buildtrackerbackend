PLAN_LIMITS = {
    'free': {
        'max_users': 10,
        'max_workspaces': 2,
        'max_storage_mb': 2048,  # 2 GB
    },
    'pro': {
        'max_users': 20,
        'max_workspaces': 10,
        'max_storage_mb': 10240,  # 10 GB
    },
    'business': {
        'max_users': 50,
        'max_workspaces': 30,
        'max_storage_mb': 102400,  # 100 GB
    },
    'enterprise': {
        'max_users': 999999,
        'max_workspaces': 999999,
        'max_storage_mb': 999999999,  # Unlimited-ish
    },
}

PLAN_DETAILS = [
    {
        'type': 'free',
        'name': 'Starter Organization',
        'price_naira': 0,
        'price_usd': 0,
        'limits': PLAN_LIMITS['free'],
        'features': ['Up to 10 users', 'Up to 2 workspaces', '2GB storage']
    },
    {
        'type': 'pro',
        'name': 'Pro Organization',
        'price_naira': 6000,
        'price_usd': 6,
        'limits': PLAN_LIMITS['pro'],
        'features': ['Up to 20 users', 'Up to 10 workspaces', '10GB storage', 'Priority support']
    },
    {
        'type': 'business',
        'name': 'Business Organization',
        'price_naira': 18000,
        'price_usd': 18,
        'limits': PLAN_LIMITS['business'],
        'features': ['Up to 50 users', 'Up to 30 workspaces', '100GB storage', '24/7 support', 'Advanced analytics']
    }
]

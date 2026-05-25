"""
BuildTracker Pricing Constants
===============================
Source of truth for plan limits, pricing, and features.
Based on BuildTracker Pricing Guide v1.0 (2025).

Plan tiers:
  free     — Forever free, no card required
  starter  — ₦9,900/mo · $6/mo (30-day trial, no card)
  premium  — ₦24,900/mo · $15/mo
  custom   — Enterprise / bespoke, quoted per client

Annual discount: pay monthly rate × 12 at a discounted monthly rate
  Starter annual:  ₦7,900/mo  →  ₦94,800/yr  ($5/mo  → $60/yr)
  Premium annual:  ₦19,900/mo → ₦238,800/yr  ($12/mo → $144/yr)
"""

# ─── Plan limits ────────────────────────────────────────────────────────────
PLAN_LIMITS = {
    'free': {
        'max_users': 2,
        'max_workspaces': 1,
        'max_storage_mb': 500,       # 500 MB
    },
    'starter': {
        'max_users': 10,
        'max_workspaces': 3,
        'max_storage_mb': 5120,      # 5 GB
    },
    'premium': {
        'max_users': 25,
        'max_workspaces': 5,
        'max_storage_mb': 20480,     # 20 GB
    },
    'custom': {
        'max_users': 999999,         # Unlimited
        'max_workspaces': 999999,    # Unlimited
        'max_storage_mb': 999999999, # Unlimited
    },
    # Legacy aliases — kept for backward compatibility with existing DB records
    'pro': {
        'max_users': 10,
        'max_workspaces': 3,
        'max_storage_mb': 5120,
    },
    'business': {
        'max_users': 25,
        'max_workspaces': 5,
        'max_storage_mb': 20480,
    },
    'enterprise': {
        'max_users': 999999,
        'max_workspaces': 999999,
        'max_storage_mb': 999999999,
    },
}

# ─── Plan details (returned by the /plans/ API) ──────────────────────────────
PLAN_DETAILS = [
    {
        'type': 'free',
        'name': 'Free',
        'tagline': 'Remove all barriers to entry.',
        'price_naira_monthly': 0,
        'price_usd_monthly': 0,
        'price_naira_yearly': 0,       # per month when billed yearly
        'price_usd_yearly': 0,
        'trial_days': 0,
        'limits': PLAN_LIMITS['free'],
        'features': [
            '1 Workspace',
            '2 Members',
            '500 MB storage',
            'Core project management tools',
            'Invite team members',
        ],
    },
    {
        'type': 'starter',
        'name': 'Starter',
        'tagline': 'Try free for 30 days. No card required.',
        'price_naira_monthly': 9900,
        'price_usd_monthly': 6,
        'price_naira_yearly': 7900,    # per month when billed yearly → ₦94,800/yr
        'price_usd_yearly': 5,         # per month when billed yearly → $60/yr
        'trial_days': 30,
        'limits': PLAN_LIMITS['starter'],
        'features': [
            'Everything in Free',
            '3 Workspaces',
            '10 Members',
            '5 GB storage',
            'Reporting & analytics',
            'Email support + priority response',
        ],
    },
    {
        'type': 'premium',
        'name': 'Premium',
        'tagline': 'Full power for growing firms.',
        'price_naira_monthly': 24900,
        'price_usd_monthly': 15,
        'price_naira_yearly': 19900,   # per month when billed yearly → ₦238,800/yr
        'price_usd_yearly': 12,        # per month when billed yearly → $144/yr
        'trial_days': 0,
        'limits': PLAN_LIMITS['premium'],
        'features': [
            'Everything in Starter',
            '5 Workspaces',
            '25 Members',
            '20 GB storage',
            'Advanced reporting & analytics',
            'Role-based permissions',
            'Third-party integrations',
            'Priority support with faster SLA',
        ],
    },
]

# ─── Custom (Enterprise) pricing formula constants ──────────────────────────
# Based on §4 of the pricing guide: Custom Pricing Formula
CUSTOM_PRICING = {
    'baseline': {
        'NGN': 24900,   # Premium plan baseline (monthly)
        'USD': 15,
    },
    # Per-unit add-on costs (monthly)
    'extra_workspace': {
        'NGN': 2000,
        'USD': 1.50,
    },
    'extra_member': {
        'NGN': 500,
        'USD': 0.30,
    },
    'extra_storage_per_10gb': {
        'NGN': 1500,
        'USD': 1.00,
    },
    # Support premium multipliers (applied to subtotal)
    'support_multiplier': {
        'standard': 1.00,       # No addition
        'priority': 1.15,       # +15%
        'dedicated': 1.25,      # +25%
    },
    # Always add negotiation buffer on top of floor price
    'negotiation_buffer': 0.25,  # +25%
    # Minimum Custom quote — never go below 3× Premium
    'minimum_quote_ngn': 75000,
    'minimum_quote_usd': 45,
}

# ─── Bank / large enterprise pricing additions ───────────────────────────────
BANK_PRICING = {
    'compliance_premium': 0.40,        # +40% on subtotal
    'enterprise_sla_premium': 0.20,    # +20% on subtotal
    'dedicated_instance_ngn': 100000,  # per month extra
    'negotiation_buffer': 0.30,        # +30% on top of everything
    'monthly_range_ngn': (400000, 800000),
    'monthly_range_usd': (250, 500),
}

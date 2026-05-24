from django.db import models
import uuid


class ContentPost(models.Model):
    PLATFORM_CHOICES = [
        ('twitter', 'Twitter/X'),
        ('instagram_post', 'Instagram Post'),
        ('instagram_slides', 'Instagram Slides'),
        ('linkedin', 'LinkedIn'),
    ]
    STATUS_CHOICES = [
        ('to_do', 'To Do'),
        ('in_progress', 'In Progress'),
        ('scheduled', 'Scheduled'),
        ('posted', 'Posted'),
        ('skipped', 'Skipped'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    id = models.AutoField(primary_key=True)
    platform = models.CharField(max_length=30, choices=PLATFORM_CHOICES)
    content_pillar = models.CharField(max_length=100, blank=True)
    tone = models.CharField(max_length=60, blank=True)
    hook = models.TextField(blank=True)
    full_copy = models.TextField(blank=True)
    visual_direction = models.TextField(blank=True)
    hashtags = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='to_do', db_index=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    # Calendar fields
    week = models.CharField(max_length=20, blank=True)
    day = models.CharField(max_length=10, blank=True)
    scheduled_date = models.DateField(null=True, blank=True)
    posted_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['platform', 'id']

    def __str__(self):
        return f"[{self.platform}] {self.hook[:60]}"


class SalesLead(models.Model):
    PRIORITY_CHOICES = [
        ('A', 'Tier A — Hot'),
        ('B', 'Tier B — Warm'),
        ('C', 'Tier C — Cold'),
    ]
    STATUS_CHOICES = [
        ('not_contacted', 'Not Contacted'),
        ('dm_sent', 'DM Sent'),
        ('replied', 'Replied'),
        ('call_booked', 'Call Booked'),
        ('demo_done', 'Demo Done'),
        ('converted', 'Converted'),
        ('not_interested', 'Not Interested'),
        ('no_response', 'No Response'),
    ]

    id = models.AutoField(primary_key=True)
    priority = models.CharField(max_length=2, choices=PRIORITY_CHOICES, default='B', db_index=True)
    company = models.CharField(max_length=200)
    website = models.CharField(max_length=200, blank=True)
    sector = models.CharField(max_length=100, blank=True, db_index=True)
    stage = models.CharField(max_length=50, blank=True, db_index=True)
    city = models.CharField(max_length=100, blank=True)
    target_title = models.CharField(max_length=300, blank=True)
    linkedin_search_url = models.TextField(blank=True)
    pain_angle = models.TextField(blank=True)
    dm_template = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_contacted', db_index=True)
    date_contacted = models.DateField(null=True, blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'company']

    def __str__(self):
        return f"[{self.priority}] {self.company}"


class LeadContact(models.Model):
    OUTREACH_STATUS_CHOICES = [
        ('not_contacted', 'Not Contacted'),
        ('dm_sent', 'DM Sent'),
        ('replied', 'Replied'),
        ('call_booked', 'Call Booked'),
        ('not_interested', 'Not Interested'),
        ('no_response', 'No Response'),
    ]

    lead = models.ForeignKey(SalesLead, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=200)
    title = models.CharField(max_length=200, blank=True)
    linkedin_url = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    twitter_handle = models.CharField(max_length=100, blank=True)
    outreach_status = models.CharField(max_length=20, choices=OUTREACH_STATUS_CHOICES, default='not_contacted')
    date_contacted = models.DateField(null=True, blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} @ {self.lead.company}"

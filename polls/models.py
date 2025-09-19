from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError


class Poll(models.Model):
    """Poll model with optimized fields for performance"""
    title = models.CharField(max_length=255, help_text="Poll question or title")
    description = models.TextField(blank=True, help_text="Optional poll description")
    created_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='created_polls'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    allow_multiple_votes = models.BooleanField(default=False)
    total_votes = models.PositiveIntegerField(default=0, db_index=True)
    
    class Meta:
        db_table = 'polls_poll'
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title
    
    @property
    def is_expired(self):
        return self.expires_at and timezone.now() > self.expires_at
    
    @property
    def can_vote(self):
        return self.is_active and not self.is_expired


class PollOption(models.Model):
    """Poll options with denormalized vote count"""
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(default=0)
    vote_count = models.PositiveIntegerField(default=0, db_index=True)
    
    class Meta:
        db_table = 'polls_option'
        ordering = ['poll', 'order']
        unique_together = ['poll', 'order']
    
    def __str__(self):
        return f"{self.poll.title} - {self.text}"


class Vote(models.Model):
    """Vote model with duplicate prevention"""
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='votes')
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='votes', null=True, blank=True)
    session_key = models.CharField(max_length=255, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'polls_vote'
        indexes = [
            models.Index(fields=['poll', 'user']),
            models.Index(fields=['poll', 'session_key']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['poll', 'user'],
                condition=models.Q(user__isnull=False),
                name='unique_user_poll_vote'
            ),
            models.UniqueConstraint(
                fields=['poll', 'session_key'],
                condition=models.Q(session_key__isnull=False),
                name='unique_session_poll_vote'
            )
        ]

def unread_notifications(request):
    """The unread count shown on the bell in the navigation bar."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    return {
        "unread_notification_count": user.notifications.filter(read_at__isnull=True).count()
    }

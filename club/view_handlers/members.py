import decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from club.models import UserProfile


@login_required
def admin_members(request):
    if not request.user.is_staff:
        messages.error(request, "Only administrators can access this page.")
        return redirect("dashboard")

    users = User.objects.filter(is_staff=False).select_related("profile").order_by(
        "-date_joined"
    )
    return render(request, "club/admin_members.html", {"users": users})


@login_required
def admin_member_edit(request, user_id):
    if not request.user.is_staff:
        messages.error(request, "Only administrators can access this page.")
        return redirect("dashboard")

    target_user = get_object_or_404(User, id=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            target_user.delete()
            messages.success(request, f"会员 {target_user.username} 已删除")
            return redirect("admin_members")
        if action == "update_balance":
            new_balance = request.POST.get("balance", "0")
            try:
                profile.balance = decimal.Decimal(new_balance)
                profile.save(update_fields=["balance"])
                messages.success(request, f"会员 {target_user.username} 余额已更新")
            except decimal.InvalidOperation:
                messages.error(request, "无效的余额数值")
        return redirect("admin_members", permanent=False)

    return render(
        request,
        "club/admin_member_edit.html",
        {
            "member": target_user,
            "profile": profile,
        },
    )

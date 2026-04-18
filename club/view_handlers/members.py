import decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from club.models import Participation, Transaction, UserProfile


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

    target_user = get_object_or_404(User, id=user_id, is_staff=False)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            target_user.delete()
            messages.success(request, f"会员 {target_user.username} 已删除")
            return redirect("admin_members")
        if action == "update_member":
            new_balance = request.POST.get("balance", "0").strip()
            try:
                target_user.username = request.POST.get("username", "").strip()
                target_user.first_name = request.POST.get("first_name", "").strip()
                target_user.last_name = request.POST.get("last_name", "").strip()
                target_user.email = request.POST.get("email", "").strip()
                target_user.is_active = request.POST.get("is_active") == "on"
                target_user.save(
                    update_fields=[
                        "username",
                        "first_name",
                        "last_name",
                        "email",
                        "is_active",
                    ]
                )
                profile.balance = decimal.Decimal(new_balance)
                profile.save(update_fields=["balance"])
                messages.success(request, f"会员 {target_user.username} 信息已更新")
            except decimal.InvalidOperation:
                messages.error(request, "无效的余额数值")
            except Exception:
                messages.error(request, "会员信息保存失败，请检查输入")
            return redirect("admin_member_edit", user_id=target_user.id)
        return redirect("admin_member_edit", user_id=target_user.id)

    return render(
        request,
        "club/admin_member_edit.html",
        {
            "member": target_user,
            "profile": profile,
            "participations": Participation.objects.filter(user=target_user)
            .select_related("event")
            .order_by("-event__date"),
            "transactions": Transaction.objects.filter(user=target_user)
            .select_related("event")
            .order_by("-created_at")[:20],
        },
    )

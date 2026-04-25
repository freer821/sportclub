from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from club.forms import AdminMemberUpdateForm, MemberProfileUpdateForm
from club.models import Participation, Transaction, UserProfile
from club.services import build_checkin_link, build_checkin_token


def _checkin_context(request, user, *, admin=False):
    token = build_checkin_token(user)
    query_string = urlencode({"token": token})
    context = {
        "checkin_link": build_checkin_link(request, user),
        "checkin_page_url": f"{reverse('qr_checkin')}?{query_string}",
    }
    if admin:
        context["checkin_qr_image_url"] = reverse(
            "admin_member_checkin_qr_svg",
            kwargs={"user_id": user.id},
        )
    else:
        context["checkin_qr_image_url"] = reverse("member_checkin_qr_svg")
    return context


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
    form = AdminMemberUpdateForm(user=target_user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            target_user.delete()
            messages.success(request, f"会员 {target_user.username} 已删除")
            return redirect("admin_members")
        if action == "update_member":
            form = AdminMemberUpdateForm(request.POST, user=target_user)
            try:
                if form.is_valid():
                    form.save()
                    messages.success(request, f"会员 {target_user.username} 信息已更新")
                else:
                    messages.error(request, "会员信息保存失败，请检查输入")
                    return render(
                        request,
                        "club/admin_member_edit.html",
                        {
                            "form": form,
                            "member": target_user,
                            "profile": profile,
                            "participations": Participation.objects.filter(user=target_user)
                            .select_related("event")
                            .order_by("-event__date"),
                            "transactions": Transaction.objects.filter(user=target_user)
                            .select_related("event")
                            .order_by("-created_at")[:20],
                            **_checkin_context(request, target_user, admin=True),
                        },
                    )
            except Exception:
                messages.error(request, "会员信息保存失败，请检查输入")
            return redirect("admin_member_edit", user_id=target_user.id)
        return redirect("admin_member_edit", user_id=target_user.id)

    return render(
        request,
        "club/admin_member_edit.html",
        {
            "form": form,
            "member": target_user,
            "profile": profile,
            "participations": Participation.objects.filter(user=target_user)
            .select_related("event")
            .order_by("-event__date"),
            "transactions": Transaction.objects.filter(user=target_user)
            .select_related("event")
            .order_by("-created_at")[:20],
            **_checkin_context(request, target_user, admin=True),
        },
    )


@login_required
def member_profile(request):
    if request.user.is_staff:
        return redirect("dashboard")

    profile = UserProfile.objects.get_or_create(user=request.user)[0]
    if request.method == "POST":
        form = MemberProfileUpdateForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "会员资料已更新")
            return redirect("member_profile")
        messages.error(request, "资料保存失败，请检查输入")
    else:
        form = MemberProfileUpdateForm(user=request.user)

    return render(
        request,
        "club/member_profile.html",
        {
            "form": form,
            "profile": profile,
            **_checkin_context(request, request.user),
        },
    )

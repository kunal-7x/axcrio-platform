"""W20 — route-surface auth-invariant tests.

Proves: every NEW W8–W16 operational route requires real tenant auth and is NOT reachable by the
legacy token after the flip; the /admin/* plane stays legacy-excluded; the manifest is internally
consistent (the regression pin for any future route)."""
from __future__ import annotations

import pytest

from voice_ops.security.principal import AuthMethod
from voice_ops.security.route_auth_assert import (
    ADMIN_ROUTES,
    W8_W16_OPERATIONAL_ROUTES,
    RouteAuthViolation,
    RouteSpec,
    all_routes,
    assert_legacy_rejected_when_off,
    assert_real_auth_passes,
    assert_route_safe,
    assert_surface_safe,
    legacy_reachable_route_paths,
)


def test_manifest_is_nonempty():
    assert len(W8_W16_OPERATIONAL_ROUTES) >= 15
    assert len(ADMIN_ROUTES) >= 1


def test_every_operational_route_requires_tenant_auth_and_forbids_legacy():
    # the structural invariant (no legacy in `accepts`, requires real tenant auth)
    paths = assert_surface_safe(all_routes())
    assert len(paths) == len(all_routes())


def test_no_route_declares_it_accepts_legacy():
    for spec in all_routes():
        assert AuthMethod.LEGACY_PW not in spec.accepts


def test_legacy_denied_on_every_operational_route_when_off():
    denied = assert_legacy_rejected_when_off(W8_W16_OPERATIONAL_ROUTES)
    assert set(denied) == {r.path for r in W8_W16_OPERATIONAL_ROUTES}


def test_legacy_denied_on_admin_routes_when_off():
    denied = assert_legacy_rejected_when_off(ADMIN_ROUTES)
    assert set(denied) == {r.path for r in ADMIN_ROUTES}


def test_real_jwt_passes_on_every_route_when_off():
    ok = assert_real_auth_passes(all_routes())
    assert set(ok) == {r.path for r in all_routes()}


def test_legacy_reachable_list_is_the_operational_non_admin_set():
    reachable = set(legacy_reachable_route_paths())
    expected = {r.path for r in W8_W16_OPERATIONAL_ROUTES if not r.is_admin_route}
    assert reachable == expected
    # the runaway-scheduler + the whatsapp pipeline + ads were all in the EXPLORE 'reachable' list
    assert "/callbacks" in reachable
    assert "/whatsapp/send" in reachable
    assert "/ads/campaigns" in reachable


# --- the regression pin: a badly-declared route fails the suite ------------------------ #
def test_route_without_tenant_auth_is_rejected():
    bad = RouteSpec("/oops", ("GET",), wave="Wx", requires_tenant_auth=False)
    with pytest.raises(RouteAuthViolation):
        assert_route_safe(bad)


def test_route_accepting_legacy_is_rejected():
    bad = RouteSpec("/oops", ("GET",), wave="Wx",
                    accepts=(AuthMethod.JWT, AuthMethod.LEGACY_PW))
    with pytest.raises(RouteAuthViolation):
        assert_route_safe(bad)


def test_admin_route_may_skip_tenant_auth_flag_but_still_no_legacy():
    # an admin route uses require_super_admin (its own auth) so requires_tenant_auth=False is OK,
    # but it must still never accept legacy.
    ok_admin = RouteSpec("/admin/x", ("GET",), wave="control", is_admin_route=True,
                         requires_tenant_auth=False, accepts=(AuthMethod.JWT,))
    assert_route_safe(ok_admin)  # no raise
    bad_admin = RouteSpec("/admin/x", ("GET",), wave="control", is_admin_route=True,
                          accepts=(AuthMethod.JWT, AuthMethod.LEGACY_PW))
    with pytest.raises(RouteAuthViolation):
        assert_route_safe(bad_admin)

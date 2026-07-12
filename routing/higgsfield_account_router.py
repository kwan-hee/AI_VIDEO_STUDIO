# 두 Higgsfield 계정(MCP 서버) 사이를 안전하게 페일오버하고 사용량을 안전 집계하는 계정 라우터
"""
Higgsfield Account Router

목적.
  - 별도 인증된 두 Higgsfield 계정(각각 별도 MCP 서버) 사이의 안전 페일오버.
  - legacy_account(기본)를 크레딧이 충분한 동안 쓰고, 소진되면 production_account 로 1회 전환.
  - 사용량을 안전하게(자격증명 없이) 집계·보고한다.

계정 alias(로그·상태에 쓰는 유일한 식별자).
  - legacy_account      → MCP 서버 higgsfield_legacy
  - production_account   → MCP 서버 higgsfield_production

보안 불변식.
  - 이메일/토큰/쿠키/API 키/계정 식별자는 코드·로그·상태·매니페스트에 절대 넣지 않는다.
  - 로그·상태에는 alias(legacy_account/production_account)만 등장한다.

안전 규칙.
  - 전환은 실행당 최대 1회. 전환 후 같은 실행에서 legacy 로 되돌아가지 않는다.
  - 인증/권한/잘못된 프롬프트/모호한 타임아웃/네트워크/잘못된 설정으로는 전환하지 않는다.
  - 크레딧 부족(사전 잔액 부족 또는 명시적 부족 오류)일 때만 전환한다.
  - 모호한 타임아웃 뒤에는 원 작업 상태를 확인하기 전까지 재제출/전환 금지(중복 유료 생성 방지).
  - 완료 작업/캐시 자산은 재사용한다.
  - backup 도 크레딧이 없으면 멈추고 보고한다.

이 모듈은 공급자를 직접 실행하지 않는다. 실제 생성은 주입된 generate_callable(mcp_call, alias)->result 가 한다.
외부 네트워크/미디어 없음.
"""

import hashlib
import json

# 실행 매니페스트(state) 안 Higgsfield 상태 블록 키.
STATE_KEY = "higgsfield_state"

_LOG_PREFIX = "[Higgsfield Router]"

_INSUFFICIENT_HINTS = (
    "insufficient", "not enough", "quota", "exhaust", "balance",
    "credit", "prepay", "prepayment", "payment required", "402",
)
_AUTH_HINTS = (
    "unauthorized", "unauthenticated", "401", "403", "forbidden",
    "permission", "auth", "login", "token expired",
)
_INVALID_HINTS = (
    "invalid prompt", "invalid_argument", "moderation", "content policy",
    "safety", "bad request", "malformed", "unsupported", "400",
)


# --- 타입 오류: generate_callable 이 올리면 문자열 추측 없이 분류된다 ---
class RouterError(Exception):
    """계정 라우터 처리 중 발생하는 최상위 오류."""


class InsufficientCreditsError(RouterError):
    """크레딧 부족/쿼터 소진/잔액 부족 — 확실한 유료 실패. 전환 대상.
    provider 가 실제 청구 크레딧을 알려주면 charged 에 담아 원장에 기록한다."""

    def __init__(self, message, charged=None):
        super().__init__(message)
        self.charged = charged


class AuthError(RouterError):
    """인증/권한 오류 — 절대 계정 전환하지 않는다."""


class InvalidRequestError(RouterError):
    """잘못된 프롬프트/모델설정/요청 — 절대 계정 전환하지 않는다."""


class AmbiguousTimeoutError(RouterError):
    """
    모호한 타임아웃 — 원 작업 상태를 확인하기 전에는 재제출/전환 금지.
    job_id: 이미 생성된 작업 id(있으면).
    check_job(): 종결 상태 조회 콜러블. 반환 예:
      {"status":"completed","result":<재사용>, "job_id":..., "charged":N}
      {"status":"insufficient"}  → 크레딧 부족 확인 → 전환 허용
      그 외/None                 → 불확실 → 멈춤(중복 유료 생성 방지)
    """

    def __init__(self, message, job_id=None, check_job=None):
        super().__init__(message)
        self.job_id = job_id
        self.check_job = check_job


def classify_error(exc):
    """예외 → "insufficient" | "auth" | "invalid" | "ambiguous". 타입 우선, 없으면 메시지 키워드.
    불확실하면 "ambiguous"(모호 실패로는 절대 전환 안 함)."""
    if isinstance(exc, InsufficientCreditsError):
        return "insufficient"
    if isinstance(exc, AuthError):
        return "auth"
    if isinstance(exc, InvalidRequestError):
        return "invalid"
    if isinstance(exc, AmbiguousTimeoutError):
        return "ambiguous"
    msg = str(getattr(exc, "message", None) or exc).lower()
    if any(h in msg for h in _AUTH_HINTS):
        return "auth"
    if any(h in msg for h in _INVALID_HINTS):
        return "invalid"
    if any(h in msg for h in _INSUFFICIENT_HINTS):
        return "insufficient"
    return "ambiguous"


def request_fingerprint(scene_id, model=None, prompt=None, params=None, preset_hash=None):
    """장면 요청의 비밀 아님 지문(재시도 판별용). 자격증명 미포함."""
    payload = json.dumps(
        {"scene": scene_id, "model": model, "prompt": prompt,
         "params": params or {}, "preset": preset_hash},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def parse_accounts(config):
    """
    higgsfield_accounts 설정(이미 파싱된 dict) 검증·정규화.
    config 는 {"higgsfield_accounts": {...}} 또는 그 내부 dict.
    starting_credit_estimate 는 참고값일 뿐, provider 잔액이 있으면 그것이 우선(권위 아님).
    비용 하드코딩 금지: 선택적 model_costs 맵만 통과.
    """
    if not isinstance(config, dict):
        raise ValueError("config 는 dict 여야 한다.")
    root = config.get("higgsfield_accounts", config)
    if not isinstance(root, dict):
        raise ValueError("higgsfield_accounts 블록이 dict 가 아니다.")

    def _acct(node, name):
        if not isinstance(node, dict):
            raise ValueError(f"{name} 계정 설정이 dict 가 아니다.")
        alias, server = node.get("alias"), node.get("mcp_server")
        if not alias or not server:
            raise ValueError(f"{name} 계정에 alias 와 mcp_server 가 필요하다.")
        return {"alias": str(alias), "mcp_server": str(server),
                "fallback_generation_limit": node.get("fallback_generation_limit"),
                "starting_credit_estimate": node.get("starting_credit_estimate")}

    if "primary" not in root or "backup" not in root:
        raise ValueError("higgsfield_accounts 에 primary 와 backup 이 모두 필요하다.")
    primary, backup = _acct(root["primary"], "primary"), _acct(root["backup"], "backup")
    if primary["alias"] == backup["alias"]:
        raise ValueError("primary 와 backup 의 alias 가 같을 수 없다.")

    fo = root.get("failover", {}) or {}
    margin = fo.get("safety_margin_credits", 0)
    try:
        margin = float(margin)
    except (TypeError, ValueError):
        margin = 0.0
    failover = {
        "enabled": bool(fo.get("enabled", True)),
        "prefer_provider_balance": bool(fo.get("prefer_provider_balance",
                                               fo.get("prefer_balance_check", True))),
        "switch_before_insufficient_balance": bool(fo.get("switch_before_insufficient_balance", True)),
        "switch_on_explicit_insufficient_credits": bool(
            fo.get("switch_on_explicit_insufficient_credits",
                   fo.get("switch_on_insufficient_credits", True))),
        "switch_on_auth_error": bool(fo.get("switch_on_auth_error", False)),
        "switch_on_timeout": bool(fo.get("switch_on_timeout", False)),
        "persist_active_account": bool(fo.get("persist_active_account", True)),
        "retry_request_after_confirmed_credit_failure": bool(
            fo.get("retry_request_after_confirmed_credit_failure",
                   fo.get("retry_original_request_after_switch", True))),
        "maximum_switches_per_run": int(fo.get("maximum_switches_per_run",
                                               fo.get("maximum_account_switches_per_run", 1))),
        "safety_margin_credits": margin,
    }
    model_costs = root.get("model_costs") or {}
    if not isinstance(model_costs, dict):
        raise ValueError("model_costs 는 dict(모델→크레딧) 여야 한다.")
    return {"primary": primary, "backup": backup, "failover": failover,
            "active_policy": root.get("active_policy", "automatic_failover"),
            "model_costs": model_costs}


class HiggsfieldAccountRouter:
    """
    두 Higgsfield 계정 페일오버 라우터 + 안전 사용량 원장.

    accounts       : parse_accounts() 결과.
    mcp_calls      : {mcp_server 이름: mcp_call(tool,args)->dict}. 계정마다 별도 transport.
    state          : 실행 매니페스트 dict. STATE_KEY 블록(active_account/switch_count/preset/completed_scenes)을 읽고(resume)·저장.
    persist        : state 저장 콜백(state)->None (전환/기록 후).
    log            : 로그 콜백(str)->None. 기본 print. alias 만.
    balance_reader : mcp_call->크레딧(float) or None. 잔액 도구 래퍼(옵션).
    cost_estimator : (model,params)->크레딧 or None. 없으면 model_costs 맵. 하드코딩 금지.
    preset         : {"name","version","hash"} 승인 프리셋 메타(옵션). 상태에 기록.
    """

    def __init__(self, accounts, mcp_calls, *, state=None, persist=None, log=None,
                 balance_reader=None, cost_estimator=None, preset=None, manual_account=None):
        self._acc = accounts
        self._primary, self._backup = accounts["primary"], accounts["backup"]
        self._fo = accounts["failover"]
        self._mcp = dict(mcp_calls or {})
        self._state = state if isinstance(state, dict) else {}
        self._persist = persist
        self._log = log or (lambda m: print(m))
        self._balance_reader = balance_reader
        self._cost_estimator = cost_estimator
        self._preset = preset

        self._hs = self._state.setdefault(STATE_KEY, {})
        self._switches = int(self._hs.get("switch_count", 0))
        self._primary_success = 0
        # 원장/집계
        self._records = self._hs.setdefault("records", [])
        self._completed = self._hs.setdefault("completed_scenes", [])
        self._reported_credits = 0.0     # provider 가 실제로 알려준 청구 합계
        self._reported_available = False # provider 잔액/청구 데이터를 한 번이라도 받았는가
        self._requested = 0
        self._completed_count = 0
        self._failed = 0
        self._by_alias = {self._primary["alias"]: 0, self._backup["alias"]: 0}
        self._dup_prevented = 0

        if preset:
            self._hs["preset"] = {"name": preset.get("name"),
                                  "version": preset.get("version"),
                                  "hash": preset.get("hash")}
            self._emit(f"Loaded approved preset in router state: "
                       f"{preset.get('name')} v{preset.get('version')}", tag="[Quality]")

        # 수동 override: 특정 계정 고정 + 자동 전환 비활성(--higgsfield-account legacy|production).
        self._manual = False
        if manual_account:
            if manual_account == self._backup["alias"]:
                self._active = self._backup
            elif manual_account == self._primary["alias"]:
                self._active = self._primary
            else:
                raise RouterError(f"알 수 없는 수동 계정 alias: {manual_account}")
            self._manual = True
            self._hs["active_account"] = self._active["alias"]
            self._emit(f"Active account: {self._active['alias']}")
            return

        # resume: 저장된 active_account 가 backup 이면 그대로 시작(소진 계정 회귀 방지).
        if self._hs.get("active_account") == self._backup["alias"]:
            self._active = self._backup
            self._switches = max(self._switches, self._fo["maximum_switches_per_run"])
        else:
            self._active = self._primary
            self._hs.setdefault("active_account", self._active["alias"])
        self._emit(f"Active account: {self._active['alias']}")

    # --- 조회 ---
    def active_alias(self):
        return self._active["alias"]

    def _mcp_for(self, account):
        call = self._mcp.get(account["mcp_server"])
        if call is None:
            raise RouterError(f"{account['alias']} 의 MCP transport 가 배선되지 않았다.")
        return call

    def _emit(self, message, tag=_LOG_PREFIX):
        self._log(f"{tag} {message}")

    # --- 전환 ---
    def _can_switch(self):
        return (not self._manual and self._fo["enabled"] and self._active is self._primary
                and self._switches < self._fo["maximum_switches_per_run"])

    def _switch(self, reason=None):
        if not self._can_switch():
            raise RouterError("추가 계정 전환 불가(상한 도달 또는 이미 production).")
        if reason:
            self._emit(reason, tag="[Credits]")
        self._switches += 1
        self._active = self._backup
        self._emit(f"Switching to {self._backup['alias']}.")
        if self._fo["persist_active_account"]:
            self._hs["active_account"] = self._backup["alias"]
            self._hs["switch_count"] = self._switches
            self._save()
            self._emit(f"Persisted active account: {self._backup['alias']}.", tag="[Resume]")

    def _save(self):
        if callable(self._persist):
            self._persist(self._state)

    # --- 잔액/비용 ---
    def _estimate_cost(self, model, params):
        if callable(self._cost_estimator):
            return self._cost_estimator(model, params)
        if model is not None:
            return self._acc["model_costs"].get(model)
        return None

    def _can_cover(self, account, model, params):
        """활성 계정이 다음 생성(비용+안전마진)을 감당하는가. True/False/None(불확실)."""
        if not self._fo["prefer_provider_balance"] or not callable(self._balance_reader):
            return None
        try:
            credits = self._balance_reader(self._mcp_for(account))
        except Exception:  # noqa: BLE001
            return None
        cost = self._estimate_cost(model, params)
        if credits is None or cost is None:
            return None
        self._reported_available = True  # provider 잔액을 실제로 받음
        need = float(cost) + float(self._fo["safety_margin_credits"])
        return float(credits) >= need

    def _over_limit(self):
        limit = self._primary.get("fallback_generation_limit")
        return limit is not None and self._primary_success >= int(limit)

    # --- 메인 실행 ---
    def run(self, generate_callable, *, model=None, params=None, prompt=None,
            scene_id=None, cache=None):
        """
        한 장면을 활성 계정으로 생성. generate_callable(mcp_call, alias)->result(dict).
        result 에서 job_id/charged/output_path 를 방어적으로 읽어 원장에 기록한다.
        """
        if not callable(generate_callable):
            raise ValueError("generate_callable 은 콜러블이어야 한다.")
        fp = request_fingerprint(scene_id, model, prompt, params,
                                 (self._preset or {}).get("hash"))

        # 0) 캐시/완료 재사용 — 중복 유료 생성 방지.
        if cache is not None and scene_id is not None and scene_id in cache:
            self._dup_prevented += 1
            self._emit(f"Reusing cached result for {scene_id}; skipping paid generation.")
            return cache[scene_id]
        if scene_id is not None and scene_id in self._completed:
            self._dup_prevented += 1
            self._emit(f"Scene {scene_id} already completed in manifest; skipping.")
            prev = self._find_record(scene_id)
            return (prev or {}).get("result")

        self._requested += 1

        # 1) 사전 잔액 확인 — primary 가 다음 생성을 못 감당하면 미리 1회 전환.
        if self._active is self._primary and self._fo["switch_before_insufficient_balance"]:
            covers = self._can_cover(self._primary, model, params)
            if covers is False and self._can_switch():
                self._switch(reason="Primary cannot cover the next confirmed request.")
            elif covers is None and self._over_limit() and self._can_switch():
                self._switch(reason="Primary reached its fallback generation limit.")

        # 2) 실행.
        result = self._invoke(generate_callable, model=model, params=params,
                              scene_id=scene_id, fingerprint=fp)

        # 3) 성공 기록.
        self._record(scene_id, fp, result, status="completed")
        if cache is not None and scene_id is not None:
            cache[scene_id] = result
        return result

    def _invoke(self, generate_callable, *, model, params, scene_id, fingerprint):
        account = self._active
        try:
            result = generate_callable(self._mcp_for(account), account["alias"])
        except Exception as exc:  # noqa: BLE001
            return self._handle_error(exc, generate_callable, model=model, params=params,
                                      scene_id=scene_id, fingerprint=fingerprint)
        if account is self._primary:
            self._primary_success += 1
        return result

    def _handle_error(self, exc, generate_callable, *, model, params, scene_id, fingerprint):
        kind = classify_error(exc)
        if kind in ("auth", "invalid"):
            self._failed += 1
            self._emit(f"Non-switchable error on {self._active['alias']} ({kind}); not switching.")
            raise exc
        if kind == "ambiguous":
            return self._handle_ambiguous(exc, generate_callable, model=model, params=params,
                                          scene_id=scene_id, fingerprint=fingerprint)
        # insufficient
        if not self._fo["switch_on_explicit_insufficient_credits"]:
            self._failed += 1
            raise exc
        if getattr(exc, "charged", None) is not None:
            self._reported_available = True
            self._reported_credits += float(exc.charged)
        if self._manual:
            # 수동 고정 계정 → 전환하지 않고 원 오류를 그대로 올린다.
            self._failed += 1
            raise exc
        if self._active is self._backup:
            self._failed += 1
            self._emit("Backup account also lacks credits; stopping.", tag="[Credits]")
            raise RouterError("두 계정 모두 크레딧 부족 — 실행 중단.") from exc
        if not self._can_switch():
            self._failed += 1
            raise exc
        self._switch(reason="Primary cannot cover the next confirmed request.")
        if not self._fo["retry_request_after_confirmed_credit_failure"]:
            self._failed += 1
            raise exc
        return self._retry_on_backup(generate_callable, scene_id=scene_id, fingerprint=fingerprint)

    def _handle_ambiguous(self, exc, generate_callable, *, model, params, scene_id, fingerprint):
        check = getattr(exc, "check_job", None)
        if not callable(check):
            self._failed += 1
            self._emit("Ambiguous timeout without job status; not retrying (avoid duplicate paid generation).")
            raise exc
        status = check() or {}
        state = str(status.get("status", "")).lower()
        if state in ("completed", "succeeded", "success", "done"):
            self._dup_prevented += 1
            self._emit("Original job already completed on timeout; reusing result (no duplicate generation).")
            res = status.get("result")
            self._record(scene_id, fingerprint, res, status="completed",
                         job_id=status.get("job_id") or getattr(exc, "job_id", None),
                         charged=status.get("charged"))
            if self._active is self._primary:
                self._primary_success += 1
            return res
        if state in ("insufficient", "insufficient_credits", "quota_exhausted"):
            if self._manual:
                self._failed += 1
                raise exc
            if self._active is self._backup or not self._can_switch():
                self._failed += 1
                self._emit("Backup account also lacks credits; stopping.", tag="[Credits]")
                raise RouterError("타임아웃 후 크레딧 부족 확인 — 전환 불가 또는 backup 소진.") from exc
            self._switch(reason="Primary cannot cover the next confirmed request.")
            return self._retry_on_backup(generate_callable, scene_id=scene_id, fingerprint=fingerprint)
        self._failed += 1
        self._emit("Original job status unresolved on timeout; not switching (avoid duplicate paid generation).")
        raise exc

    def _retry_on_backup(self, generate_callable, *, scene_id, fingerprint):
        account = self._backup
        try:
            result = generate_callable(self._mcp_for(account), account["alias"])
        except Exception as exc:  # noqa: BLE001
            if classify_error(exc) == "insufficient":
                self._failed += 1
                self._emit("Backup account also lacks credits; stopping.", tag="[Credits]")
                raise RouterError("backup 재시도에서도 크레딧 부족 — 실행 중단.") from exc
            raise
        return result

    # --- 원장 ---
    def _find_record(self, scene_id):
        for r in self._records:
            if r.get("scene_id") == scene_id:
                return r
        return None

    def _record(self, scene_id, fingerprint, result, *, status, job_id=None, charged=None):
        alias = self._active["alias"]
        job_id = job_id or (result.get("job_id") if isinstance(result, dict) else None)
        charged = charged if charged is not None else (
            result.get("charged") if isinstance(result, dict) else None)
        output_path = result.get("output") or result.get("path") if isinstance(result, dict) else None
        if charged is not None:
            self._reported_available = True
            self._reported_credits += float(charged)
        rec = {
            "scene_id": scene_id, "fingerprint": fingerprint, "job_id": job_id,
            "account_alias": alias, "preset_version": (self._preset or {}).get("version"),
            "status": status, "output_path": output_path,
        }
        # 같은 scene 재기록 방지(멱등)
        existing = self._find_record(scene_id) if scene_id is not None else None
        if existing:
            existing.update(rec)
        else:
            self._records.append(rec)
        if status == "completed":
            self._completed_count += 1
            self._by_alias[alias] = self._by_alias.get(alias, 0) + 1
            if scene_id is not None and scene_id not in self._completed:
                self._completed.append(scene_id)
        self._save()

    # --- 안전 사용량 요약 (reported vs estimated 명확 구분) ---
    def usage_summary(self, project=None, image_motion_fallback_scenes=0):
        primary_est = self._primary.get("starting_credit_estimate")
        remaining_estimate = None
        if primary_est is not None and not self._reported_available:
            remaining_estimate = float(primary_est) - self._reported_credits
        return {
            "project": project,
            "approved_preset": (f"{self._preset['name']} v{self._preset['version']}"
                                if self._preset else None),
            "paid_generations_requested": self._requested,
            "paid_generations_completed": self._completed_count,
            "paid_generations_failed": self._failed,
            "legacy_account_generations": self._by_alias.get(self._primary["alias"], 0),
            "production_account_generations": self._by_alias.get(self._backup["alias"], 0),
            "account_switches": self._switches,
            "duplicate_requests_prevented": self._dup_prevented,
            "image_motion_fallback_scenes": image_motion_fallback_scenes,
            "provider_reported_credits": (
                self._reported_credits if self._reported_available else "unavailable"),
            "estimated_remaining_balance": (
                remaining_estimate if remaining_estimate is not None else "estimate only"),
            "credit_data_source": ("provider_reported" if self._reported_available
                                   else "local_estimate"),
        }

    def print_usage_summary(self, project=None, image_motion_fallback_scenes=0):
        s = self.usage_summary(project, image_motion_fallback_scenes)
        lines = [
            "Higgsfield usage summary",
            "------------------------",
            f"Project: {s['project']}",
            f"Approved preset: {s['approved_preset']}",
            f"Paid generations requested: {s['paid_generations_requested']}",
            f"Paid generations completed: {s['paid_generations_completed']}",
            f"Paid generations failed: {s['paid_generations_failed']}",
            f"Legacy account generations: {s['legacy_account_generations']}",
            f"Production account generations: {s['production_account_generations']}",
            f"Account switches: {s['account_switches']}",
            f"Duplicate requests prevented: {s['duplicate_requests_prevented']}",
            f"Image-motion fallback scenes: {s['image_motion_fallback_scenes']}",
            f"Provider-reported credits used: {s['provider_reported_credits']}",
            f"Estimated remaining balance: {s['estimated_remaining_balance']} "
            f"({'estimate only' if s['credit_data_source'] == 'local_estimate' else 'provider-reported'})",
        ]
        self._log("\n".join(lines))
        return s


def make_balance_reader(tool_name="balance", field_candidates=("credits", "balance", "available")):
    """잔액 MCP 도구 래퍼 mcp_call->크레딧(float or None). 실 Higgsfield balance 는 {credits,...} 반환."""
    def _read(mcp_call):
        resp = mcp_call(tool_name, {})
        if not isinstance(resp, dict):
            return None
        for key in field_candidates:
            if resp.get(key) is not None:
                try:
                    return float(resp[key])
                except (TypeError, ValueError):
                    return None
        return None
    return _read


if __name__ == "__main__":
    demo = {
        "higgsfield_accounts": {
            "active_policy": "automatic_failover",
            "primary": {"alias": "legacy_account", "mcp_server": "higgsfield_legacy",
                        "starting_credit_estimate": 823},
            "backup": {"alias": "production_account", "mcp_server": "higgsfield_production",
                       "starting_credit_estimate": 6000},
            "failover": {"enabled": True, "maximum_switches_per_run": 1,
                         "safety_margin_credits": 100},
        }
    }
    print(json.dumps(parse_accounts(demo), ensure_ascii=False, indent=2))

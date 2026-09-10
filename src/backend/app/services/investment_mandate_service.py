"""Investment mandate parsing and persistence for AI research."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from app.db import database
from app.models.ai_research import InvestmentMandate
from app.schemas.ai_strategy_research import (
    AIStrategyResearchRunRequest,
    InvestmentMandateCreate,
    InvestmentMandateResponse,
    normalize_market_data_asset_type,
)

_MANDATE_REQUEST_MISMATCH_CODE = "INVESTMENT_MANDATE_REQUEST_MISMATCH"
_AUTO_BASIS_SCHEMA_VERSION = "investment-mandate-auto-basis-v1"
_LEGACY_DEFAULT_INITIAL_CASH = 100000.0
_LEGACY_QUALITY_GATE_DEFAULTS: dict[str, Any] = {
    "robustness_validation": False,
    "require_robustness_validation": False,
    "robustness_methods": ["monte_carlo"],
    "min_robustness_score": 55.0,
    "robustness_monte_carlo_iterations": 300,
    "robustness_random_seed": None,
}


class InvestmentMandateService:
    """Parse natural-language investment demand into a confirmed mandate."""

    async def create_mandate(
        self,
        user_id: str,
        data: InvestmentMandateCreate,
    ) -> InvestmentMandateResponse:
        parsed = self.parse_mandate(data)
        model = InvestmentMandate(
            user_id=user_id,
            raw_prompt=parsed["raw_prompt"],
            structured_goal=parsed["structured_goal"],
            asset_scope=parsed["asset_scope"],
            timeframe=parsed.get("timeframe"),
            objective=parsed.get("objective"),
            risk_constraints=parsed["risk_constraints"],
            trading_constraints=parsed["trading_constraints"],
            quality_gates=parsed["quality_gates"],
            status="confirmed",
            source="rule",
        )
        async with database.async_session_maker() as session:
            session.add(model)
            await session.commit()
            await session.refresh(model)
        return self._to_response(model)

    async def ensure_for_request(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
    ) -> InvestmentMandateResponse:
        if request.mandate_id:
            mandate = await self.get_mandate(user_id, request.mandate_id)
            if mandate is None:
                raise ValueError("Investment mandate not found")
            if not self._request_matches_mandate(mandate, request):
                # A mandate is an authorization for a concrete research basis,
                # rather than a reusable label. Keep this as a stable ValueError
                # code so service callers and the HTTP boundary can reject a
                # tampered direct request without exposing mandate contents.
                raise ValueError(_MANDATE_REQUEST_MISMATCH_CODE)
            return mandate

        return await self.create_mandate(
            user_id,
            InvestmentMandateCreate(
                raw_prompt=request.prompt,
                prompt_origin=self._request_prompt_origin(request),
                symbol=request.symbol,
                symbol_name=request.symbol_name,
                market_data_asset_type=self._market_data_asset_type_from_request(request),
                timeframe=request.timeframe,
                risk_constraints=self._risk_constraints_from_request(request),
                trading_constraints={
                    "initial_cash": request.initial_cash,
                    "annual_days": request.annual_days,
                    "calc_method": request.calc_method,
                    "weight_mode": request.weight_mode,
                    "start_paper_trading": request.start_paper_trading,
                },
                quality_gates=self._quality_gates_from_request(request),
            ),
        )

    async def restore_auto_continuation_request(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        trusted_auto_prompt: str | None = None,
        trusted_auto_mandate_id: str | None = None,
    ) -> AIStrategyResearchRunRequest:
        """Rebuild a verified auto-mandate continuation without a historical prompt.

        Persisted run records and task snapshots store Pydantic's generated
        prompt text, which would otherwise look like a new explicit prompt on
        reconstruction.  The route supplies the server-persisted source prompt
        only when its explicit-field metadata proves that source omitted a
        prompt.  A caller override may be cleared only when it is exactly that
        source text and still refers to the source mandate; any other prompt
        remains explicit and must be authorized as such.
        """
        source_prompt = str(trusted_auto_prompt or "").strip()
        source_mandate_id = str(trusted_auto_mandate_id or "").strip()
        if (
            not request.mandate_id
            or request.workflow_mode != "auto"
            or not source_prompt
            or not source_mandate_id
            or request.mandate_id != source_mandate_id
            or request.prompt.strip() != source_prompt
        ):
            return request
        mandate = await self.get_mandate(user_id, request.mandate_id)
        if mandate is None or not self._matches_server_auto_basis(mandate, request):
            return request
        payload = request.model_dump(mode="python")
        payload.pop("prompt", None)
        return AIStrategyResearchRunRequest.model_validate(payload)

    async def get_mandate(
        self,
        user_id: str,
        mandate_id: str,
    ) -> InvestmentMandateResponse | None:
        async with database.async_session_maker() as session:
            result = await session.execute(
                select(InvestmentMandate).where(
                    InvestmentMandate.id == mandate_id,
                    InvestmentMandate.user_id == user_id,
                )
            )
            model = result.scalar_one_or_none()
        return self._to_response(model) if model else None

    def parse_mandate(self, data: InvestmentMandateCreate) -> dict[str, Any]:
        prompt = data.raw_prompt.strip()
        # An auto-workflow prompt preview is client-side display text, not an
        # authorization input.  Derive its basis exclusively from the typed
        # controls that are later bound to the run request.
        prompt_basis = "" if data.prompt_origin == "auto_generated" else prompt
        symbol = (data.symbol or self._symbol_from_prompt(prompt_basis) or "").strip()
        asset_class = self._asset_class(symbol, prompt_basis)
        asset_scope = {
            "asset_class": asset_class,
            "symbol": symbol,
            "symbol_name": (data.symbol_name or "").strip(),
        }
        if data.market_data_asset_type is not None:
            asset_scope["market_data_asset_type"] = data.market_data_asset_type
        timeframe = (
            data.timeframe or self._timeframe_from_prompt(prompt_basis) or ""
        ).strip() or None
        objective = (data.objective or self._objective_from_prompt(prompt_basis)).strip()
        risk_constraints = {
            **self._risk_constraints_from_prompt(prompt_basis),
            **dict(data.risk_constraints or {}),
        }
        trading_constraints = {
            **self._trading_constraints_from_prompt(prompt_basis, asset_class),
            **dict(data.trading_constraints or {}),
        }
        quality_gates = dict(data.quality_gates or {})
        structured_goal = {
            "asset_class": asset_class,
            "symbol": symbol,
            "symbol_name": (data.symbol_name or "").strip(),
            "timeframe": timeframe,
            "objective": objective,
            "prompt_origin": data.prompt_origin,
            "risk_focus": sorted(risk_constraints),
            "quality_gates": quality_gates,
        }
        raw_prompt = prompt
        if data.prompt_origin == "auto_generated":
            structured_goal["auto_basis_schema_version"] = _AUTO_BASIS_SCHEMA_VERSION
            auto_basis_digest = self._auto_basis_digest(
                asset_scope=asset_scope,
                timeframe=timeframe,
                risk_constraints=risk_constraints,
                trading_constraints=self._controlled_trading_constraints_from_mapping(
                    trading_constraints
                ),
                quality_gates=quality_gates,
            )
            structured_goal["auto_basis_digest"] = auto_basis_digest
            # Never store a browser-provided auto preview as if it were the
            # approved objective. The server display is reproducible from the
            # same normalized basis that authorizes a later blank request.
            raw_prompt = self._server_auto_prompt_preview(
                asset_scope=asset_scope,
                timeframe=timeframe,
                auto_basis_digest=auto_basis_digest,
            )
            objective = self._server_auto_objective(auto_basis_digest)
            structured_goal["objective"] = objective
        return {
            "raw_prompt": raw_prompt,
            "structured_goal": structured_goal,
            "asset_scope": asset_scope,
            "timeframe": timeframe,
            "objective": objective,
            "risk_constraints": risk_constraints,
            "trading_constraints": trading_constraints,
            "quality_gates": quality_gates,
        }

    def _quality_gates_from_request(self, request: AIStrategyResearchRunRequest) -> dict[str, Any]:
        return {
            "target_sharpe": request.target_sharpe,
            "min_total_trades": request.min_total_trades,
            "max_drawdown_limit": request.max_drawdown_limit,
            "min_total_return": request.min_total_return,
            "min_annual_return": request.min_annual_return,
            "min_win_rate": request.min_win_rate,
            "out_of_sample_validation": request.out_of_sample_validation,
            "require_out_of_sample_validation": request.require_out_of_sample_validation,
            "out_of_sample_ratio": request.out_of_sample_ratio,
            "min_out_of_sample_sharpe": request.min_out_of_sample_sharpe,
            "min_out_of_sample_trades": request.min_out_of_sample_trades,
            "robustness_validation": request.robustness_validation,
            "require_robustness_validation": request.require_robustness_validation,
            "robustness_methods": list(request.robustness_methods),
            "min_robustness_score": request.min_robustness_score,
            "robustness_monte_carlo_iterations": request.robustness_monte_carlo_iterations,
            "robustness_random_seed": request.robustness_random_seed,
        }

    def _risk_constraints_from_request(
        self,
        request: AIStrategyResearchRunRequest,
    ) -> dict[str, Any]:
        # These are the same request-controlled fields persisted by the UI's
        # confirmed-mandate flow. Store explicit null/false values as part of
        # the approval basis instead of treating their absence as permission
        # to alter a later request.
        return {
            "max_drawdown_limit": request.max_drawdown_limit,
            "min_win_rate": request.min_win_rate,
            "out_of_sample_validation": request.out_of_sample_validation,
        }

    def _request_matches_mandate(
        self,
        mandate: InvestmentMandateResponse,
        request: AIStrategyResearchRunRequest,
    ) -> bool:
        """Return whether a confirmed mandate authorizes this exact request basis.

        Auto workflow requests may omit ``prompt`` and receive a server-generated
        objective during Pydantic validation. In that one case, the prompt is
        intentionally not a caller-controlled value to compare; every asset,
        risk, trading, and quality field remains bound to the mandate.
        """
        structured_goal = dict(mandate.structured_goal or {})
        is_auto_mandate = structured_goal.get("prompt_origin") == "auto_generated"
        if is_auto_mandate:
            # An auto-origin mandate only authorizes the typed blank-auto
            # request.  Even the server-owned audit preview is not a user
            # objective that can be replayed as an explicit prompt; doing so
            # would let a client turn an auto mandate into a prompt mandate.
            if request.workflow_mode != "auto" or self._request_has_explicit_prompt(request):
                return False
            if not self._matches_server_auto_basis(mandate, request):
                return False
        elif self._request_has_explicit_prompt(request):
            if not self._value_matches(mandate.raw_prompt.strip(), request.prompt.strip()):
                return False
        else:
            # A blank request has no investor-authored objective. It cannot
            # reuse a mandate that was confirmed from an explicit prompt.
            return False

        asset_scope = dict(mandate.asset_scope or {})
        mandate_symbol = self._normalized_asset_value(asset_scope.get("symbol"))
        request_symbol = self._normalized_asset_value(request.symbol)
        if not mandate_symbol or mandate_symbol != request_symbol:
            return False

        mandate_symbol_name = self._normalized_display_value(asset_scope.get("symbol_name"))
        if mandate_symbol_name and mandate_symbol_name != self._normalized_display_value(
            request.symbol_name
        ):
            return False

        mandate_timeframe = self._normalized_asset_value(
            mandate.timeframe or mandate.structured_goal.get("timeframe")
        )
        if not mandate_timeframe or mandate_timeframe != self._normalized_asset_value(
            request.timeframe
        ):
            return False

        try:
            request_asset_type = self._market_data_asset_type_from_request(request)
            mandate_asset_type = (
                normalize_market_data_asset_type(asset_scope.get("market_data_asset_type"))
                if "market_data_asset_type" in asset_scope
                else None
            )
        except ValueError:
            return False
        # A final bridge marker is attached only after a fresh capability
        # decision.  Until then, a confirmed mandate may use the Iter196
        # fallback path without losing its recorded asset scope.  Once a
        # marker is present, however, it must exactly match the confirmed
        # scope; an old mandate without a scope cannot authorize a new family.
        if request_asset_type is not None and mandate_asset_type != request_asset_type:
            return False

        return (
            self._risk_constraints_match(
                mandate.risk_constraints,
                self._risk_constraints_from_request(request),
            )
            and self._trading_constraints_match(
                mandate.trading_constraints,
                self._controlled_trading_constraints_from_request(request),
            )
            and self._quality_gates_match(
                mandate.quality_gates,
                self._quality_gates_from_request(request),
            )
        )

    @staticmethod
    def _risk_constraints_match(
        actual: dict[str, Any] | None,
        expected: dict[str, Any],
    ) -> bool:
        """Normalize the known pre-197 out-of-sample representation before comparing.

        Older server-created mandates represented enabled out-of-sample validation
        as ``{"ratio": ..., "required": ...}`` under the risk key and omitted the
        key when disabled. The detailed ratio/required controls were already kept
        in ``quality_gates`` and remain checked there.
        """
        if actual is None:
            return False
        normalized = dict(actual)
        old_out_of_sample = normalized.get("out_of_sample_validation")
        if isinstance(old_out_of_sample, dict):
            normalized["out_of_sample_validation"] = True
        elif "out_of_sample_validation" not in normalized:
            normalized["out_of_sample_validation"] = False
        return InvestmentMandateService._constraint_record_matches(normalized, expected)

    @staticmethod
    def _trading_constraints_match(
        actual: dict[str, Any] | None,
        expected: dict[str, Any],
    ) -> bool:
        """Normalize only the known legacy omission of initial cash.

        Pre-197 automatic mandate creation did not persist ``initial_cash``.
        Its historical execution default was 100000, so a legacy record may
        authorize that value only; a caller choosing another amount must create
        and confirm a fresh mandate.
        """
        if actual is None:
            return False
        normalized = dict(actual)
        normalized.setdefault("initial_cash", _LEGACY_DEFAULT_INITIAL_CASH)
        return InvestmentMandateService._constraint_record_matches(normalized, expected)

    @staticmethod
    def _quality_gates_match(
        actual: dict[str, Any] | None,
        expected: dict[str, Any],
    ) -> bool:
        """Normalize only robustness fields absent from the known legacy writer.

        This is a narrow read-time schema migration, not a blanket fallback:
        every other missing quality gate remains a mismatch. A caller that asks
        for non-default robustness controls must confirm a new mandate.
        """
        if actual is None:
            return False
        normalized = dict(actual)
        for key, default in _LEGACY_QUALITY_GATE_DEFAULTS.items():
            if key not in normalized:
                normalized[key] = list(default) if isinstance(default, list) else default
        return InvestmentMandateService._constraint_record_matches(normalized, expected)

    @staticmethod
    def _request_has_explicit_prompt(request: AIStrategyResearchRunRequest) -> bool:
        fields_set = getattr(request, "model_fields_set", set())
        return isinstance(fields_set, set) and "prompt" in fields_set

    @classmethod
    def _request_prompt_origin(cls, request: AIStrategyResearchRunRequest) -> str:
        return "explicit" if cls._request_has_explicit_prompt(request) else "auto_generated"

    def _auto_basis_digest_for_request(
        self,
        request: AIStrategyResearchRunRequest,
        *,
        market_data_asset_type: str | None = None,
    ) -> str:
        """Return the server-side auto mandate digest for one normalized request."""
        asset_scope = {
            "asset_class": self._asset_class(request.symbol, ""),
            "symbol": self._normalized_asset_value(request.symbol),
            "symbol_name": self._normalized_display_value(request.symbol_name),
        }
        resolved_market_data_asset_type = (
            market_data_asset_type
            if market_data_asset_type is not None
            else self._market_data_asset_type_from_request(request)
        )
        if resolved_market_data_asset_type is not None:
            asset_scope["market_data_asset_type"] = resolved_market_data_asset_type
        return self._auto_basis_digest(
            asset_scope=asset_scope,
            timeframe=self._normalized_asset_value(request.timeframe),
            risk_constraints=self._risk_constraints_from_request(request),
            trading_constraints=self._controlled_trading_constraints_from_request(request),
            quality_gates=self._quality_gates_from_request(request),
        )

    def _matches_server_auto_basis(
        self,
        mandate: InvestmentMandateResponse,
        request: AIStrategyResearchRunRequest,
    ) -> bool:
        """Return whether a mandate carries the current server-issued auto basis."""
        structured_goal = dict(mandate.structured_goal or {})
        stored_digest = structured_goal.get("auto_basis_digest")
        asset_scope = dict(mandate.asset_scope or {})
        try:
            market_data_asset_type = (
                normalize_market_data_asset_type(asset_scope.get("market_data_asset_type"))
                if "market_data_asset_type" in asset_scope
                else None
            )
        except ValueError:
            return False
        return (
            structured_goal.get("prompt_origin") == "auto_generated"
            and structured_goal.get("auto_basis_schema_version") == _AUTO_BASIS_SCHEMA_VERSION
            and self._is_auto_basis_digest(stored_digest)
            and hmac.compare_digest(
                stored_digest,
                self._auto_basis_digest_for_request(
                    request,
                    market_data_asset_type=market_data_asset_type,
                ),
            )
        )

    @staticmethod
    def _controlled_trading_constraints_from_mapping(
        constraints: dict[str, Any],
    ) -> dict[str, Any]:
        """Select only mandate-controlled trading fields from a persisted mapping."""
        return {
            "initial_cash": constraints.get("initial_cash"),
            "annual_days": constraints.get("annual_days"),
            "calc_method": constraints.get("calc_method"),
            "weight_mode": constraints.get("weight_mode"),
        }

    @staticmethod
    def _is_auto_basis_digest(value: Any) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )

    @staticmethod
    def _auto_basis_digest(
        *,
        asset_scope: dict[str, Any],
        timeframe: str | None,
        risk_constraints: dict[str, Any],
        trading_constraints: dict[str, Any],
        quality_gates: dict[str, Any],
    ) -> str:
        """Hash only the normalized controls that authorize auto workflow reuse."""
        material = {
            "schema_version": _AUTO_BASIS_SCHEMA_VERSION,
            "asset_scope": InvestmentMandateService._canonical_auto_basis_value(asset_scope),
            "timeframe": InvestmentMandateService._canonical_auto_basis_value(timeframe or ""),
            "risk_constraints": InvestmentMandateService._canonical_auto_basis_value(
                risk_constraints
            ),
            "trading_constraints": InvestmentMandateService._canonical_auto_basis_value(
                trading_constraints
            ),
            "quality_gates": InvestmentMandateService._canonical_auto_basis_value(quality_gates),
        }
        canonical = json.dumps(
            material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_auto_basis_value(value: Any) -> Any:
        """Normalize JSON-compatible control values before hashing an auto basis."""
        if value is None or isinstance(value, (bool, str)):
            return value
        if isinstance(value, (int, float)):
            try:
                decimal = Decimal(str(value))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError("INVESTMENT_MANDATE_AUTO_BASIS_INVALID") from exc
            if not decimal.is_finite():
                raise ValueError("INVESTMENT_MANDATE_AUTO_BASIS_INVALID")
            if decimal == 0:
                return "0"
            return format(decimal.normalize(), "f")
        if isinstance(value, list):
            return [InvestmentMandateService._canonical_auto_basis_value(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): InvestmentMandateService._canonical_auto_basis_value(item)
                for key, item in value.items()
            }
        raise ValueError("INVESTMENT_MANDATE_AUTO_BASIS_INVALID")

    @staticmethod
    def _server_auto_prompt_preview(
        *,
        asset_scope: dict[str, Any],
        timeframe: str | None,
        auto_basis_digest: str,
    ) -> str:
        """Render a server-owned display objective for an auto mandate."""
        symbol = str(asset_scope.get("symbol") or "").strip()
        symbol_name = str(asset_scope.get("symbol_name") or "").strip()
        subject = symbol_name or symbol or str(asset_scope.get("asset_class") or "标的")
        symbol_suffix = f"（{symbol}）" if symbol and symbol_name else ""
        period = str(timeframe or "1d").strip() or "1d"
        return (
            f"服务器自动生成投研目标：{subject}{symbol_suffix}，{period}；"
            f"授权基准 {auto_basis_digest}。"
        )

    @staticmethod
    def _server_auto_objective(auto_basis_digest: str) -> str:
        """Return the server-owned objective persisted for an auto mandate."""
        return f"服务器自动生成的投研目标（授权基准 {auto_basis_digest}）"

    @staticmethod
    def _normalized_asset_value(value: Any) -> str:
        # Market-data identity treats imported instrument spelling as exact:
        # RB0 and rb0 may resolve to different approved identities.
        return str(value or "").strip()

    @staticmethod
    def _normalized_display_value(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _market_data_asset_type_from_request(
        request: AIStrategyResearchRunRequest,
    ) -> str | None:
        """Read the only permitted market-data intent from a research request.

        ``data_config`` remains the existing bounded bridge input.  A mandate
        does not accept a parallel unvalidated top-level field, and a supplied
        value must pass the same seven-family whitelist as a direct mandate.
        """
        data_config = request.data_config
        if not isinstance(data_config, dict) or "market_data_asset_type" not in data_config:
            return None
        return normalize_market_data_asset_type(data_config["market_data_asset_type"])

    @staticmethod
    def _controlled_trading_constraints_from_request(
        request: AIStrategyResearchRunRequest,
    ) -> dict[str, Any]:
        # Starting paper trading and choosing a workspace are operational
        # continuation choices. They do not rewrite the investor-approved
        # research mandate.
        return {
            "initial_cash": request.initial_cash,
            "annual_days": request.annual_days,
            "calc_method": request.calc_method,
            "weight_mode": request.weight_mode,
        }

    @classmethod
    def _constraint_record_matches(
        cls,
        actual: dict[str, Any] | None,
        expected: dict[str, Any],
    ) -> bool:
        if actual is None:
            return False
        # ``None`` is a meaningful, persisted approval value for several
        # controls. A missing key must therefore never compare equal to an
        # expected ``None`` through ``dict.get``. Callers that support a known
        # legacy schema omission normalize that exact key before reaching this
        # shared comparison; every remaining missing record fails closed.
        return all(
            key in actual and cls._value_matches(actual[key], value)
            for key, value in expected.items()
        )

    @classmethod
    def _value_matches(cls, actual: Any, expected: Any) -> bool:
        if isinstance(expected, list):
            return (
                isinstance(actual, list)
                and len(actual) == len(expected)
                and all(cls._value_matches(item, expected[index]) for index, item in enumerate(actual))
            )
        if isinstance(expected, dict):
            return isinstance(actual, dict) and cls._constraint_record_matches(actual, expected)
        return actual == expected or (actual is None and expected is None)

    def _symbol_from_prompt(self, prompt: str) -> str:
        match = re.search(
            r"\b[A-Z]{1,4}\d{0,4}(?:\.(?:SZ|SH|BJ|SHFE|DCE|CZCE|INE|CFFEX))?\b", prompt
        )
        return match.group(0) if match else ""

    def _timeframe_from_prompt(self, prompt: str) -> str:
        normalized = prompt.lower()
        patterns = (
            (r"(\d+)\s*h|(\d+)\s*小时", "h"),
            (r"(\d+)\s*d|(\d+)\s*日", "d"),
            (r"(\d+)\s*min|(\d+)\s*分钟", "m"),
        )
        for pattern, suffix in patterns:
            match = re.search(pattern, normalized)
            if not match:
                continue
            number = next(group for group in match.groups() if group)
            return f"{number}{suffix}"
        if "日线" in prompt or "daily" in normalized:
            return "1d"
        if "小时" in prompt or "hour" in normalized:
            return "1h"
        return ""

    def _asset_class(self, symbol: str, prompt: str) -> str:
        text = f"{symbol} {prompt}".upper()
        if any(token in prompt for token in ("期货", "合约", "纯碱", "螺纹", "原油", "国债期货")):
            return "futures"
        if any(token in prompt for token in ("股票", "个股", "A股")) or text.endswith(
            (".SZ", ".SH", ".BJ")
        ):
            return "equity"
        if any(token in prompt for token in ("债券", "国债", "利率债")):
            return "bond"
        if any(token in prompt for token in ("基金", "ETF")):
            return "fund"
        if any(token in prompt for token in ("期权", "波动率曲面")):
            return "option"
        if any(token in prompt for token in ("外汇", "汇率")):
            return "fx"
        if any(token in text for token in ("USDT", "BTC", "ETH", "PERP", "SWAP")):
            return "crypto"
        return "multi_asset"

    def _objective_from_prompt(self, prompt: str) -> str:
        if any(token in prompt for token in ("保值", "稳健", "低回撤", "回撤")):
            return "稳健增值并控制回撤"
        if any(token in prompt for token in ("套利", "价差", "跨期")):
            return "捕捉相对价值或期限价差机会"
        if any(token in prompt for token in ("趋势", "突破")):
            return "捕捉趋势收益并控制反转风险"
        return prompt[:300]

    def _risk_constraints_from_prompt(self, prompt: str) -> dict[str, Any]:
        constraints: dict[str, Any] = {}
        if "回撤" in prompt:
            constraints["drawdown_control"] = True
        if any(token in prompt for token in ("止损", "风险")):
            constraints["stop_loss_required"] = True
        if any(token in prompt for token in ("样本外", "过拟合")):
            constraints["out_of_sample_required"] = True
        return constraints

    def _trading_constraints_from_prompt(self, prompt: str, asset_class: str) -> dict[str, Any]:
        constraints: dict[str, Any] = {"asset_class": asset_class}
        if asset_class == "futures":
            constraints["requires_contract_specs"] = True
            constraints["requires_margin_sizing"] = True
        if any(token in prompt for token in ("手续费", "滑点")):
            constraints["requires_cost_model"] = True
        return constraints

    def _to_response(self, model: InvestmentMandate) -> InvestmentMandateResponse:
        return InvestmentMandateResponse(
            id=model.id,
            raw_prompt=model.raw_prompt,
            structured_goal=dict(model.structured_goal or {}),
            asset_scope=dict(model.asset_scope or {}),
            timeframe=model.timeframe,
            objective=model.objective,
            risk_constraints=dict(model.risk_constraints or {}),
            trading_constraints=dict(model.trading_constraints or {}),
            quality_gates=dict(model.quality_gates or {}),
            status=model.status,
            source=model.source,
            created_at=_iso(model.created_at),
            updated_at=_iso(model.updated_at),
        )


def _iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else ""

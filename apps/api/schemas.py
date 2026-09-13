"""Pydantic schemas for the Bhoomi Raksha API.

Every analytical value the UI shows arrives through one of these. Provenance
and data-quality fields are part of the contract, not an afterthought: a number
without its source is not shippable in this product.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["critical", "high", "monitor", "safe"]
# Architecture accepts several hazards; only "landslide" has a pipeline today.
HazardType = Literal["landslide", "earthquake", "flood", "cyclone"]
ScreeningStatus = Literal["FEASIBLE", "REVIEW", "REJECTED"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]


class Provenance(BaseModel):
    """Where a value came from and how far it can be trusted."""
    source: str
    source_resolution: str | None = None
    processing: str | None = None
    validation_status: str
    proxy: bool = False
    limitations: list[str] = Field(default_factory=list)


class DataQuality(BaseModel):
    confidence: Confidence
    reasons: list[str]
    footprint_source: str | None = None
    population_source: str
    hazard_validation: str
    accessibility_method: str


class Contribution(BaseModel):
    id: str
    label: str
    component_score: float
    weight: float
    contribution: float
    evidence: str


class Explanation(BaseModel):
    method: str = "Transparent Weighted Contribution"
    note: str
    contributions: list[Contribution]
    total: float


class HazardBasisFactor(BaseModel):
    factor: str
    label: str
    weight: float = Field(description="share of the susceptibility index, not model accuracy")


class HazardModel(BaseModel):
    """What a hazard-specific risk number is built from."""
    type: HazardType
    label: str
    index_label: str
    susceptibility_label: str
    model_name: str
    method: str
    assessment: str
    basis: list[HazardBasisFactor]
    hazard_mean_weight: float
    hazard_peak_weight: float
    risk_weights: dict[str, float]
    risk_labels: dict[str, str]
    validated: bool
    meaning: str


class HazardAssessment(BaseModel):
    type: HazardType
    mean_susceptibility: float | None
    peak_susceptibility: float | None
    hazard_component: float


class RegionSummary(BaseModel):
    hazard_type: HazardType
    hazard_model: HazardModel
    name: str
    code: str
    state: str
    area_km2: float
    primary_hazard: str
    settlements: int
    district_population: int
    district_exposed_population: int
    settlement_population: int
    settlement_exposed_population: int
    levels: dict[str, int]
    red_zone_area_km2: float
    candidate_sites: int
    feasible_sites: int
    updated_at: str
    model_version: str
    provenance: list[Provenance]
    disclaimer: str


class HabitationSummary(BaseModel):
    id: str
    name: str
    place: str | None
    lon: float
    lat: float
    population: int
    exposed_population: int
    exposed_area_percent: float | None
    mean_hazard: float | None
    max_hazard: float | None
    risk_score: float
    level: RiskLevel
    priority_rank: int
    priority_score: float
    confidence: Confidence
    hazard_type: HazardType


class HabitationDetail(HabitationSummary):
    hazard_model: HazardModel
    hazard: HazardAssessment
    risk_display: int = Field(description="risk_score rounded half-up for display")
    site_slope_mean_deg: float | None
    dist_to_road_m: float | None
    dist_to_major_road_m: float | None
    dist_to_health_m: float | None
    footprint_source: str
    analysed_area_km2: float | None
    components: dict[str, float]
    contributions: dict[str, float]
    explanation: Explanation
    data_quality: DataQuality
    recommendation: str


class CapacityConstraint(BaseModel):
    name: str
    capacity: int
    derivation: str
    is_binding: bool


class CandidateSite(BaseModel):
    candidate_id: str
    lon: float
    lat: float
    area_km2: float
    mean_susceptibility: float
    max_susceptibility: float
    mean_slope_deg: float
    distance_to_road_m: float
    distance_to_major_road_m: float
    distance_to_healthcare_m: float
    current_population: int
    suitability_score: float
    screening_status: ScreeningStatus
    safety_score: float
    terrain_score: float
    road_access_score: float
    healthcare_access_score: float
    effective_capacity: int
    available_capacity: int
    binding_constraint: str
    constraints: list[CapacityConstraint]
    distance_from_habitation_km: float | None = None


class Allocation(BaseModel):
    source_id: str
    source_name: str
    site_id: str
    population: int
    distance_km: float
    site_suitability: float


class SiteUtilisation(BaseModel):
    site_id: str
    allocated: int
    available_capacity: int
    utilisation_percent: float


class OptimizationResult(BaseModel):
    solver_status: str
    objective_value: float
    allocations: list[Allocation]
    total_relocated: int
    unallocated_population: int
    unmet_by_source: list[dict] = Field(default_factory=list)
    site_utilization: list[SiteUtilisation]
    constraint_summary: list[str]
    sources: int
    sinks: int
    config: dict
    objective_description: str


class OptimizationRequest(BaseModel):
    habitation_ids: list[str] | None = None
    max_distance_km: float = 40.0
    allow_review_sites: bool = False


class ScenarioRequest(BaseModel):
    rainfall_delta_percent: float = 0.0
    population_delta_percent: float = 0.0
    road_availability_percent: float = 100.0


class ScenarioDelta(BaseModel):
    label: str
    baseline: float
    scenario: float
    delta: float
    unit: str = ""


class ScenarioResponse(BaseModel):
    parameters: ScenarioRequest
    deltas: list[ScenarioDelta]
    baseline_levels: dict[str, int]
    scenario_levels: dict[str, int]
    changed_habitations: list[dict]
    top_priority_baseline: str
    top_priority_scenario: str
    optimization: OptimizationResult
    propagation_notes: list[str]
    runtime_ms: int


class ExecutiveBrief(BaseModel):
    region: str
    primary_hazard: str
    hazard_type: HazardType
    index_label: str
    habitation: HabitationSummary
    observed: dict
    derived: dict
    recommended: dict
    preferred_site: CandidateSite | None
    optimization: OptimizationResult | None
    scenario_note: str | None
    data_confidence: Confidence
    confidence_reasons: list[str]
    limitations: list[str]
    disclaimer: str
    generated_at: str
    model_version: str

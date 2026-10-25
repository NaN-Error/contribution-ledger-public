from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field
from app.auth.schemas import Input, Name, Reason
from app.policies.schemas import AtomCount, PositiveAtoms, VersionNumber, Category, PoolKey, Hash


class InitialBudget(Input):
    kind: Literal['initial_budget']
    total_atoms: PositiveAtoms
    reserve_floor_atoms: AtomCount


class SetBudget(Input):
    kind: Literal['set_budget']
    total_atoms: PositiveAtoms
    reserve_floor_atoms: AtomCount


class Allocate(Input):
    kind: Literal['allocate']
    title: Name
    category: Category
    pool_key: PoolKey
    atoms: PositiveAtoms


class ResizeAllocation(Input):
    kind: Literal['resize_allocation']
    allocation_id: UUID
    atoms: PositiveAtoms


class CancelAllocation(Input):
    kind: Literal['cancel_allocation']
    allocation_id: UUID


BudgetChange = Annotated[InitialBudget | SetBudget | Allocate | ResizeAllocation | CancelAllocation,
                         Field(discriminator='kind')]


class MilestoneCreate(Input):
    name: Name
    description: str = Field(default='', max_length=1000)
    policy_id: UUID
    total_atoms: PositiveAtoms
    reserve_floor_atoms: AtomCount
    reason: Reason


class AmendmentCreate(Input):
    expected_version: VersionNumber
    change: BudgetChange
    reason: Reason


class AmendmentDecision(Input):
    decision: Literal['approve', 'reject']
    expected_version: VersionNumber
    reviewed_preview_hash: Hash
    reason: Reason

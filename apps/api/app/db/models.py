from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class DevelopmentMarker(Base):
    """Synthetic operator-created record. Not a user, contribution, or financial record."""
    __tablename__ = "development_markers"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

# Register phase-2 models for migrations and metadata checks.
from app.auth.models import User, BrowserSession, InstallationState, RecoveryToken, ThrottleBucket  # noqa: F401,E402
from app.projects.models import Workspace, WorkspaceMembership, Project, ProjectMembership, Invitation, AuditEvent  # noqa: F401,E402

# Register immutable policies and planning budgets. No contribution ledger yet.
from app.policies.models import PolicyVersion, PolicyParticipant, PolicyApproval, PolicyAcknowledgement  # noqa: F401,E402
from app.contributions.budgets.models import Milestone, BudgetAllocation, BudgetAmendment, BudgetDecision  # noqa: F401,E402

# Work-package snapshots and submission history. These do not issue credit.
from app.contributions.work_packages.models import WorkPackage, WorkPackageRevision, WorkPackageParticipant, WorkPackageEvent, WorkSubmission  # noqa: F401,E402

# Manual evidence, private artifacts and immutable review packets.
from app.evidence.models import EvidenceItem, EvidenceObject, EvidenceRevision, EvidenceRetirement, EvidenceSnapshot  # noqa: F401,E402

# Phase 6: immutable human decisions, ledger events and correction records.
from app.reviews.models import (ReviewRound, ReviewAssignment, ReviewDecision, CreditDispute, DisputeAssignment, DisputeNote, DisputeResolution, ParticipantNotification)  # noqa: F401,E402
from app.ledger.models import CreditAward, ContributionEvent, ContributionBalance  # noqa: F401,E402

from app.finance.simulator.models import SimulationScenario  # noqa: F401

from app.integrations.github.models import (GitHubAuthFlow, GitHubConnection, GitHubRepository, GitHubImport,
    GitHubFetchTask, GitHubSourceVersion, GitHubObservation, GitHubIdentity, GitHubIdentityDecision, GitHubEvidenceLink)  # noqa: F401
from app.jobs.models import OutboxMessage  # noqa: F401
from app.integrations.github.sync_models import (WebhookDelivery, WebhookTarget, GitHubSyncConfig,
    GitHubSyncRun, GitHubSourceHead, JobHeartbeat)  # noqa: F401

from app.ai.models import (AIConnection, AIModel, AIPrice, AIUsageBucket, AIJob, AIEvent, AIProfile, AIProfileApproval, AIUsageResolution)  # noqa: F401

from app.ai.assessments.models import (AIReviewPacket, AIReviewPlan, AIReviewGrant, AIReviewRevocation, AIReviewResult, AIReviewFeedback)  # noqa: F401

from app.contributions.reconstruction.models import (ReconstructionBatch, ReconstructionCandidate, ReconstructionSourceClaim, ReconstructionEvent, ReconstructionMissingClaim, OpeningBalanceSnapshot)  # noqa: F401

# Phase 13: immutable finance evidence, decisions, snapshots and external declarations.
from app.finance.periods.models import (FinancePeriod, FinanceDocument, FinanceEntry,
    FinanceEntryDecision, ReleaseShareSnapshot, FinanceProposal, FinanceApproval,
    DistributionClose, ExternalPayment, PaymentVoid)  # noqa: F401
from app.finance.periods.models import FinanceReceiptImport  # noqa: F401

from app.auth.mfa_models import Authenticator  # noqa: F401
from app.auth.desktop import DesktopProfile  # noqa: F401

from app.analysis.models import (RepositoryAnalysis, AnalysisDraft, AnalysisDraftRevision,
    AnalysisPublication, AnalysisPublicationRevocation, AnalysisHandoff, AnalysisSourceClaim, RepositoryReadConnection)  # noqa: F401

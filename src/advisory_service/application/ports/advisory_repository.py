"""
추천 결과 저장을 위한 포트 (인터페이스).

domain이 아니라 application 계층에 둔다. "도메인이 요구하는 계약"이라기보다
"GenerateAdvisoryUseCase가 결과를 어디에 어떻게 내보낼지"를 정의하는
출력 포트(output port)에 가깝기 때문이다. 실제 구현(PostgreSQL 등)은
infrastructure/persistence/repositories/postgres_advisory_repository.py 가 담당한다.

save_many가 investor_profile을 함께 받는 이유: recommendations.user_id는
user_profiles(user_id)를 참조하는 FK다. 이 서비스가 사용자 프로필을
별도 upsert하는 경로가 없으면 첫 추천 저장에서 FK 위반이 발생하므로,
저장 직전에 프로필을 함께 upsert해 이 서비스 로컬 테이블 안에서 FK가
항상 만족되도록 한다. (User Service가 사용자 자체의 원본이라는 점은
변하지 않음 — 이 테이블은 free_text_query 등 이 서비스가 필요로 하는
투자성향 컨텍스트를 위한 로컬 스냅샷일 뿐이다.)
"""

from collections.abc import Sequence
from typing import Protocol

from advisory_service.domain.models.advisory import AdvisoryRecommendation
from advisory_service.domain.models.investor_profile import InvestorProfile


class AdvisoryRepository(Protocol):
    async def save_many(
        self,
        recommendations: Sequence[AdvisoryRecommendation],
        investor_profile: InvestorProfile,
    ) -> None:
        """
        investor_profile을 user_profiles에 upsert한 뒤, 추천 결과 여러 건을
        같은 트랜잭션으로 영속화한다.
        """
        ...

"""application.ports.narrative_generator.NarrativeGeneratorPort의 OpenAI 구현체."""

from openai import AsyncOpenAI

from advisory_service.domain.models.candidate import ScoredCandidate

MODEL = "gpt-4o-mini"  # 개발 예산 대비 비용 효율적 (narrative 500건 생성 시 약 $0.07 수준 추정)


class OpenAINarrativeGenerator:
    def __init__(self, client: AsyncOpenAI):
        self._client = client

    async def generate(self, candidate: ScoredCandidate) -> str:
        prompt = self._build_prompt(candidate)
        response = await self._client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        return response.choices[0].message.content or ""

    @staticmethod
    def _build_prompt(candidate: ScoredCandidate) -> str:
        b = candidate.score_breakdown
        return (
            f"종목: {candidate.name_kr} ({candidate.stock_code})\n"
            f"적합도 세부점수: 밸류에이션 {b.get('valuation_fit', 0):.2f}, "
            f"수익성 {b.get('profitability_fit', 0):.2f}, "
            f"변동성 {b.get('volatility_fit', 0):.2f}\n"
            "위 수치를 근거로, 왜 이 종목이 사용자에게 적합한지 2~3문장으로 설명하라. "
            "수치를 지어내지 말고 주어진 세부점수만 근거로 사용하라."
        )

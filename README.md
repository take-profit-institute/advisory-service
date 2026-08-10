# Advisory Service

## Architecture

The source tree follows a layered dependency rule:

```text
transport ─┐
           ├──> application ──> domain
infrastructure ─┘
```

- `domain`: business models, scoring policies, and persistence contracts. It
  does not import frameworks or infrastructure.
- `application`: advisory use cases and LangGraph orchestration. External
  capabilities are expressed as ports.
- `infrastructure`: PostgreSQL, OpenAI, retrieval, and stock-catalog adapters.
- `transport`: gRPC server and request/response mapping.
- `bootstrap.py`: the composition root that wires adapters to application
  services.

Generated gRPC modules live under `transport/grpc/generated` and must not be
imported by the domain or application layers.

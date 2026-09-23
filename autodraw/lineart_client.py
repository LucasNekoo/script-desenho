"""
Cliente do autodraw-lineart (extração de line art por IA), contrato v1.

A ferramenta roda em processo separado e tem o próprio ambiente Python com
PyTorch; o AutoDraw só a executa e lê a resposta. Especificação do contrato:
docs/contrato.md na branch `autodraw-lineart`. Este arquivo é a cópia do
cliente de referência de lá (examples/cliente_autodraw.py), no estilo deste
projeto; só usa a biblioteca padrão.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

SUPPORTED_CONTRACT = 1

# Sem isso, no Windows, cada chamada abriria uma janela de console por cima do jogo.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LineartError(Exception):
    """Falha da ferramenta. `kind` segue o campo "error" do contrato.

    Além dos tipos do contrato (weights, input, usage, unexpected), o cliente
    usa: missing (não instalada), timeout, protocol (resposta ilegível) e
    contract (versão de contrato não suportada).
    """

    def __init__(self, kind: str, message: str, exit_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.exit_code = exit_code


@dataclass
class LineartResult:
    output: Path
    model: str
    width: int
    height: int
    seconds: Dict[str, float] = field(default_factory=dict)


class LineartClient:
    """Executa o `autodraw-lineart` e interpreta a resposta JSON."""

    def __init__(self, command: Sequence[str], weights_dir: Optional[Path] = None) -> None:
        self.command = list(command)
        self.weights_dir = weights_dir

    def available(self, model: str = "default") -> bool:
        """Rápido (~30 ms): não carrega o PyTorch nem calcula o SHA-256.

        Serve para decidir se a opção de IA aparece. A conferência completa dos
        pesos acontece de qualquer forma em extract().
        """
        try:
            self.check(model)
            return True
        except LineartError:
            return False

    def check(self, model: str = "default") -> Dict:
        return self._run(["check", "--model", model, "--skip-verify"], timeout=15)

    def extract(self, image: Path, out: Path, model: str = "default", size: int = 512,
                threads: Optional[int] = None, timeout: float = 120.0) -> LineartResult:
        args = ["extract", str(image), "--out", str(out), "--model", model, "--size", str(size)]
        if threads:
            args += ["--threads", str(threads)]
        payload = self._run(args, timeout=timeout)
        return LineartResult(output=Path(payload["output"]), model=payload["model"],
                             width=payload["width"], height=payload["height"],
                             seconds=payload.get("seconds", {}))

    def _run(self, args: List[str], timeout: float) -> Dict:
        if not self.command:
            raise LineartError("missing", "autodraw-lineart não encontrado.")
        if self.weights_dir is not None:
            args = [*args, "--weights-dir", str(self.weights_dir)]
        try:
            proc = subprocess.run([*self.command, *args], capture_output=True, text=True,
                                  timeout=timeout, creationflags=_NO_WINDOW)
        except OSError as exc:  # inclui arquivo inexistente e sem permissão
            raise LineartError("missing", f"Não foi possível executar o autodraw-lineart: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise LineartError("timeout", f"O autodraw-lineart não respondeu em {timeout:.0f} s.") from exc

        lines = proc.stdout.strip().splitlines()
        if not lines:
            detail = proc.stderr.strip()[-300:]
            raise LineartError("protocol", f"Nenhuma resposta do autodraw-lineart "
                                           f"(código {proc.returncode}): {detail}", proc.returncode)
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise LineartError("protocol", f"Resposta inesperada do autodraw-lineart: {lines[-1][:200]}",
                               proc.returncode) from exc
        if payload.get("contract") != SUPPORTED_CONTRACT:
            raise LineartError("contract", f"O autodraw-lineart usa o contrato {payload.get('contract')}, "
                                           f"mas este AutoDraw entende o {SUPPORTED_CONTRACT}. "
                                           f"Atualize os dois.", proc.returncode)
        if not payload.get("ok"):
            raise LineartError(payload.get("error", "unexpected"), payload.get("message", ""),
                               proc.returncode)
        return payload

"""
Cliente de referência do contrato v1: é assim que o AutoDraw deve chamar a ferramenta.

Usa só a biblioteca padrão, então o AutoDraw não ganha nenhuma dependência.
Copie esta classe para o AutoDraw em vez de importar este pacote: a ideia é
justamente que o AutoDraw não precise ter o autodraw-lineart instalado no
mesmo ambiente.

Uso direto: python cliente_autodraw.py <imagem> <saida.png>
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_CONTRACT = 1

# Sem isso, no Windows, cada chamada abriria uma janela de console por cima do jogo.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LineartError(Exception):
    """Falha da ferramenta. `kind` segue o campo "error" do contrato.

    Além dos tipos do contrato (weights, input, usage, unexpected), o cliente
    usa: missing (não instalado), timeout, protocol (resposta ilegível) e
    contract (versão de contrato não suportada).
    """

    def __init__(self, kind: str, message: str, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.exit_code = exit_code


@dataclass
class LineartResult:
    output: Path
    model: str
    width: int
    height: int
    seconds: dict


class LineartClient:
    """Chama o executável `autodraw-lineart` em processo separado."""

    def __init__(self, command: Sequence[str] | None = None, weights_dir: Path | None = None) -> None:
        if command is None:
            exe = shutil.which("autodraw-lineart")
            command = [exe] if exe else []
        self.command = list(command)
        self.weights_dir = weights_dir

    def available(self, model: str = "default") -> bool:
        """Rápido (~30 ms): não carrega o PyTorch nem calcula o SHA-256.

        Serve para decidir se a opção de IA aparece na interface. A conferência
        completa dos pesos acontece de qualquer forma em extract().
        """
        try:
            self._run(["check", "--model", model, "--skip-verify"], timeout=15)
            return True
        except LineartError:
            return False

    def extract(self, image: Path, out: Path, model: str = "default", size: int = 512,
                threads: int | None = None, timeout: float = 120.0) -> LineartResult:
        args = ["extract", str(image), "--out", str(out), "--model", model, "--size", str(size)]
        if threads:
            args += ["--threads", str(threads)]
        payload = self._run(args, timeout=timeout)
        return LineartResult(output=Path(payload["output"]), model=payload["model"],
                             width=payload["width"], height=payload["height"], seconds=payload["seconds"])

    def _run(self, args: list[str], timeout: float) -> dict:
        if not self.command:
            raise LineartError("missing", "autodraw-lineart não está instalado (não está no PATH).")
        if self.weights_dir is not None:
            args = [*args, "--weights-dir", str(self.weights_dir)]
        try:
            proc = subprocess.run([*self.command, *args], capture_output=True, text=True,
                                  timeout=timeout, creationflags=_NO_WINDOW)
        except FileNotFoundError as exc:
            raise LineartError("missing", f"executável não encontrado: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise LineartError("timeout", f"sem resposta em {timeout:.0f} s") from exc

        lines = proc.stdout.strip().splitlines()
        if not lines:
            raise LineartError("protocol", f"nenhuma resposta JSON (código {proc.returncode}): "
                                           f"{proc.stderr.strip()[-300:]}", proc.returncode)
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise LineartError("protocol", f"resposta não é JSON: {lines[-1][:200]}",
                               proc.returncode) from exc
        if payload.get("contract") != SUPPORTED_CONTRACT:
            raise LineartError("contract", f"contrato {payload.get('contract')} não suportado "
                                           f"(este cliente entende o {SUPPORTED_CONTRACT})", proc.returncode)
        if not payload.get("ok"):
            raise LineartError(payload.get("error", "unexpected"), payload.get("message", ""),
                               proc.returncode)
        return payload


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    client = LineartClient()
    if not client.available():
        sys.exit("autodraw-lineart indisponível: instale e rode 'autodraw-lineart download'.")
    result = client.extract(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"{result.output} ({result.width}×{result.height}) em {sum(result.seconds.values()):.2f} s")

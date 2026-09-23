"""
Interface de linha de comando: o contrato com o autodraw.

Cada chamada imprime exatamente uma linha JSON no stdout (mensagens de
progresso vão para o stderr) e termina com um destes códigos:

    0  sucesso
    1  erro inesperado
    2  argumentos inválidos (argparse)
    3  pesos ausentes ou diferentes dos publicados
    4  imagem de entrada inválida

O campo "contract" do JSON muda só quando o formato mudar de forma incompatível.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import __version__
from .weights import ENV_WEIGHTS_DIR, MODELS, WeightsError, default_weights_dir, download, weights_path

SIZE_STEP = 256  # igual a extract.SIZE_STEP; repetido para não importar numpy/PIL no check

CONTRACT = 1

EXIT_OK, EXIT_UNEXPECTED, EXIT_USAGE, EXIT_WEIGHTS, EXIT_INPUT = 0, 1, 2, 3, 4


class UsageError(Exception):
    """Argumentos inválidos; vira resposta JSON em vez do texto padrão do argparse."""


class _Parser(argparse.ArgumentParser):
    """ArgumentParser que não imprime nem sai sozinho em erro de argumento.

    `--help` e `--version` continuam em texto: são para pessoas, não para o AutoDraw.
    """

    def error(self, message: str):
        raise UsageError(f"{self.prog}: {message}")


def default_threads() -> int:
    """Metade dos núcleos, no máximo 4: o jogo roda na mesma máquina."""
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def _emit(payload: dict) -> None:
    payload = {"contract": CONTRACT, "version": __version__, **payload}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _fail(code: int, kind: str, message: str) -> int:
    _emit({"ok": False, "error": kind, "message": message})
    return code


def _cmd_extract(args: argparse.Namespace) -> int:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(args.input) as src:
            src.load()
            image = src.copy()
    except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:
        return _fail(EXIT_INPUT, "input", f"Não foi possível abrir {args.input}: {exc}")

    t0 = time.perf_counter()
    import torch

    from .extract import extract_lines, load_model

    torch.set_num_threads(args.threads)
    try:
        net = load_model(args.model, args.weights_dir, verify=not args.skip_verify)
    except WeightsError as exc:
        return _fail(EXIT_WEIGHTS, "weights", str(exc))
    t1 = time.perf_counter()
    lines = extract_lines(net, image, args.size)
    t2 = time.perf_counter()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines.save(out)
    _emit({"ok": True, "output": str(out), "model": args.model, "size": args.size,
           "threads": args.threads, "width": lines.width, "height": lines.height,
           "seconds": {"load": round(t1 - t0, 3), "inference": round(t2 - t1, 3)}})
    return EXIT_OK


def _cmd_check(args: argparse.Namespace) -> int:
    models = {}
    for name in MODELS:
        try:
            path = weights_path(name, args.weights_dir, verify=not args.skip_verify)
            models[name] = {"ok": True, "path": str(path)}
        except WeightsError as exc:
            models[name] = {"ok": False, "message": str(exc)}
    ok = models[args.model]["ok"]
    payload = {"ok": ok, "weights_dir": str(args.weights_dir or default_weights_dir()), "models": models}
    if not ok:  # mesma forma de qualquer outro erro: "error" e "message" no topo
        payload.update(error="weights", message=models[args.model]["message"])
    _emit(payload)
    return EXIT_OK if ok else EXIT_WEIGHTS


def _cmd_download(args: argparse.Namespace) -> int:
    try:
        path = download(args.model, args.weights_dir)
    except WeightsError as exc:
        return _fail(EXIT_WEIGHTS, "weights", str(exc))
    _emit({"ok": True, "model": args.model, "path": str(path)})
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="autodraw-lineart",
                     description="Extrai line art de ilustrações (Anime2Sketch, CPU).")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    common = _Parser(add_help=False)
    common.add_argument("--model", choices=sorted(MODELS), default="default")
    common.add_argument("--weights-dir", type=Path, default=None,
                        help=(f"pasta dos pesos (padrão: ${ENV_WEIGHTS_DIR} ou "
                              f"{default_weights_dir()})"))
    common.add_argument("--skip-verify", action="store_true",
                        help="pula o SHA-256 (só tamanho); mais rápido, menos seguro")
    sub = parser.add_subparsers(dest="command", required=True)

    ext = sub.add_parser("extract", parents=[common], help="gera a imagem de linhas")
    ext.add_argument("input")
    ext.add_argument("--out", required=True)
    ext.add_argument("--size", type=int, default=512, help="lado de processamento, múltiplo de 256")
    ext.add_argument("--threads", type=int, default=default_threads())
    ext.set_defaults(func=_cmd_extract)

    chk = sub.add_parser("check", parents=[common], help="confere se os pesos estão presentes e íntegros")
    chk.set_defaults(func=_cmd_check)

    dl = sub.add_parser("download", parents=[common], help="baixa e confere os pesos")
    dl.set_defaults(func=_cmd_download)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except UsageError as exc:
        return _fail(EXIT_USAGE, "usage", str(exc))
    size = getattr(args, "size", None)
    if size is not None and (size < SIZE_STEP or size % SIZE_STEP):
        return _fail(EXIT_USAGE, "usage", f"--size precisa ser múltiplo de {SIZE_STEP}.")
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 — o autodraw precisa sempre de uma resposta JSON
        return _fail(EXIT_UNEXPECTED, "unexpected", f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())

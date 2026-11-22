"""Storage de estáticos compatível com os vendors empacotados.

O Bootstrap distribuído em ``static/vendor`` referencia
``bootstrap.bundle.min.js.map``, que não é versionado. O backend padrão do
WhiteNoise levanta erro nessa referência e aborta o ``collectstatic``. Este
backend mantém hash de conteúdo e compressão, mas tolera referências ausentes
dentro de arquivos JS/CSS; templates continuam estritos (manifest_strict).
"""

from __future__ import annotations

from whitenoise.storage import CompressedManifestStaticFilesStorage


class LenientCompressedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Mantém o manifest estrito para templates e ignora vendors incompletos."""

    def make_helpful_exception(self, exception, name):
        if isinstance(exception, ValueError) and "could not be found" in str(exception):
            # Referência ausente dentro de um vendor (ex.: source map do
            # Bootstrap): o arquivo é publicado sem o ajuste da referência.
            return False
        return super().make_helpful_exception(exception, name)

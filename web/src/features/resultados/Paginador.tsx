import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'

interface Props {
  pagina: number
  tamPagina: number
  total: number
  onCambiar: (pagina: number) => void
}

export function Paginador({ pagina, tamPagina, total, onCambiar }: Props) {
  const { t } = useTranslation('resultados')
  const totalPaginas = Math.max(1, Math.ceil(total / tamPagina))

  return (
    <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
      <Button variant="outline" size="sm" disabled={pagina <= 1} onClick={() => onCambiar(pagina - 1)}>
        {t('paginacion.anterior')}
      </Button>
      <span className="tabular">{t('paginacion.pagina', { pagina, total: totalPaginas })}</span>
      <Button variant="outline" size="sm" disabled={pagina >= totalPaginas} onClick={() => onCambiar(pagina + 1)}>
        {t('paginacion.siguiente')}
      </Button>
      <span className="ml-auto tabular">{t('paginacion.total', { total })}</span>
    </div>
  )
}

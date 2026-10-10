import { BellRing, ChartColumn, Megaphone, Tag, TriangleAlert, Users, type LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { MetricasBacktest } from './tipos'

/** Lectura defensiva de `resumen` (es `additionalProperties: true` en la API): cada bloque puede
 * faltar según los tipos de análisis pedidos, así que todo es opcional. */
interface Resumen {
  totales?: { clientes?: number; productos?: number; filas?: number }
  recompra?: { recordatorios?: number; clientes?: number }
  riesgo?: { clientes?: number; pares?: number; valor_en_riesgo_tienda?: number }
  ofertas?: { ofertas?: number; clientes?: number }
  contactar?: { por_decision?: { contactar?: number; revisar?: number } }
}

interface Kpi {
  clave: string
  icono: LucideIcon
  etiqueta: string
  valor: string
  detalle?: string
  tono: 'primario' | 'riesgo' | 'neutro'
}

const TONO_ICONO: Record<Kpi['tono'], string> = {
  primario: 'bg-accent text-accent-foreground',
  riesgo: 'bg-danger-soft text-danger',
  neutro: 'bg-muted text-muted-foreground',
}

function numero(valor: unknown): number | null {
  return typeof valor === 'number' && Number.isFinite(valor) ? valor : null
}

interface Props {
  resumen: Record<string, unknown> | null | undefined
  metricas: MetricasBacktest | null
}

/** Fila de indicadores arriba de los resultados, con lo que ya trae `GET /analisis/{id}`
 * (`resumen` y `metricas` del backtest). Solo muestra los que existen. */
export function KpisAnalisis({ resumen: resumenCrudo, metricas }: Props) {
  const { t, i18n } = useTranslation('panel')
  const entero = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 0 })
  const compacto = new Intl.NumberFormat(i18n.language, { notation: 'compact', maximumFractionDigits: 1 })
  const decimal = new Intl.NumberFormat(i18n.language, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const porcentaje = new Intl.NumberFormat(i18n.language, { style: 'percent', maximumFractionDigits: 0 })
  const resumen = (resumenCrudo ?? {}) as Resumen
  const kpis: Kpi[] = []

  const clientes = numero(resumen.totales?.clientes)
  if (clientes != null) {
    const productos = numero(resumen.totales?.productos)
    const filas = numero(resumen.totales?.filas)
    kpis.push({
      clave: 'clientes',
      icono: Users,
      etiqueta: t('kpis.clientes'),
      valor: entero.format(clientes),
      detalle:
        productos != null && filas != null
          ? t('kpis.clientes_sub', { productos: compacto.format(productos), filas: compacto.format(filas) })
          : undefined,
      tono: 'neutro',
    })
  }

  const recordatorios = numero(resumen.recompra?.recordatorios)
  if (recordatorios != null) {
    const conClientes = numero(resumen.recompra?.clientes)
    kpis.push({
      clave: 'recordatorios',
      icono: BellRing,
      etiqueta: t('kpis.recordatorios'),
      valor: entero.format(recordatorios),
      detalle: conClientes != null ? t('kpis.recordatorios_sub', { clientes: entero.format(conClientes) }) : undefined,
      tono: 'primario',
    })
  }

  const enRiesgo = numero(resumen.riesgo?.clientes)
  if (enRiesgo != null) {
    const valor = numero(resumen.riesgo?.valor_en_riesgo_tienda)
    const pares = numero(resumen.riesgo?.pares)
    kpis.push({
      clave: 'riesgo',
      icono: TriangleAlert,
      etiqueta: t('kpis.riesgo'),
      valor: entero.format(enRiesgo),
      detalle:
        valor != null && valor > 0
          ? t('kpis.riesgo_sub', { valor: compacto.format(valor) })
          : pares != null
            ? t('kpis.riesgo_sub_simple', { pares: entero.format(pares) })
            : undefined,
      tono: 'riesgo',
    })
  }

  const ofertas = numero(resumen.ofertas?.ofertas)
  if (ofertas != null) {
    const conClientes = numero(resumen.ofertas?.clientes)
    kpis.push({
      clave: 'ofertas',
      icono: Tag,
      etiqueta: t('kpis.ofertas'),
      valor: entero.format(ofertas),
      detalle: conClientes != null ? t('kpis.ofertas_sub', { clientes: entero.format(conClientes) }) : undefined,
      tono: 'primario',
    })
  }

  const aContactar = numero(resumen.contactar?.por_decision?.contactar)
  if (aContactar != null) {
    const revisar = numero(resumen.contactar?.por_decision?.revisar) ?? 0
    kpis.push({
      clave: 'contactar',
      icono: Megaphone,
      etiqueta: t('kpis.contactar'),
      valor: entero.format(aContactar),
      detalle: t('kpis.contactar_sub', { revisar: entero.format(revisar) }),
      tono: 'primario',
    })
  }

  const precision = numero(metricas?.modelo?.precision_at_k?.media)
  const brier = numero(metricas?.modelo?.brier?.media)
  const brierBase = numero(metricas?.linea_base?.brier?.media)
  if (precision != null || brier != null) {
    kpis.push({
      clave: 'precision',
      icono: ChartColumn,
      etiqueta: precision != null ? t('kpis.precision') : t('kpis.brier'),
      valor: precision != null ? porcentaje.format(precision) : decimal.format(brier as number),
      detalle:
        brier != null
          ? t('kpis.precision_sub', {
              brier: decimal.format(brier),
              base: brierBase != null ? decimal.format(brierBase) : '—',
            })
          : undefined,
      tono: 'neutro',
    })
  }

  if (kpis.length === 0) return null

  return (
    <section aria-label={t('kpis.aria')}>
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {kpis.map(({ clave, icono: Icono, etiqueta, valor, detalle, tono }) => (
          <div key={clave} className="flex flex-col rounded-xl border bg-card p-4 shadow-xs">
            <div className="flex items-start justify-between gap-2">
              <dt className="text-xs font-medium leading-snug text-muted-foreground">{etiqueta}</dt>
              <span
                className={`inline-flex size-7 shrink-0 items-center justify-center rounded-md ${TONO_ICONO[tono]}`}
              >
                <Icono aria-hidden="true" className="size-3.5" />
              </span>
            </div>
            <dd className="mt-2 text-2xl font-semibold tracking-tight tabular">{valor}</dd>
            {detalle && <dd className="mt-1 text-xs leading-snug text-muted-foreground">{detalle}</dd>}
          </div>
        ))}
      </dl>
    </section>
  )
}

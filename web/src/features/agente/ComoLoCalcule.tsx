import { useTranslation } from 'react-i18next'

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { ConsultaAgente } from './hooks'
import { resaltarSql } from './resaltarSql'

function TablaFilas({ consulta }: { consulta: ConsultaAgente }) {
  const { t } = useTranslation('agente')
  if (consulta.filas_muestra.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('consulta.sin_filas')}</p>
  }
  const columnas = Object.keys(consulta.filas_muestra[0])
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {columnas.map((columna) => (
            <TableHead key={columna}>{columna}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {consulta.filas_muestra.map((fila, indice) => (
          <TableRow key={indice}>
            {columnas.map((columna) => (
              <TableCell key={columna}>{String(fila[columna] ?? '')}</TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** Desplegable "cómo lo calculé" (FR-22): cada consulta SQL que de verdad corrió, resaltada, con
 * su muestra de filas — para que el número de la respuesta se pueda verificar. */
export function ComoLoCalcule({ consultas }: { consultas: ConsultaAgente[] }) {
  const { t } = useTranslation('agente')
  if (consultas.length === 0) return null

  return (
    <details className="mt-2 rounded-md border p-3">
      <summary className="cursor-pointer text-sm font-medium">{t('como_lo_calcule')}</summary>
      <div className="mt-3 space-y-4">
        {consultas.map((consulta, indice) => (
          <div key={indice} className="space-y-2">
            <pre className="overflow-x-auto rounded-md bg-muted p-2 text-xs">
              <code>{resaltarSql(consulta.sql)}</code>
            </pre>
            <p className="text-xs text-muted-foreground">
              {t('consulta.n_filas', { n: consulta.n_filas })}
            </p>
            <TablaFilas consulta={consulta} />
          </div>
        ))}
      </div>
    </details>
  )
}

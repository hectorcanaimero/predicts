import type { ReactNode } from 'react'

const PALABRAS_CLAVE = [
  'SELECT', 'FROM', 'WHERE', 'GROUP BY', 'ORDER BY', 'LIMIT', 'OFFSET', 'JOIN', 'LEFT JOIN',
  'RIGHT JOIN', 'INNER JOIN', 'OUTER JOIN', 'ON', 'AS', 'WITH', 'AND', 'OR', 'NOT', 'IN', 'LIKE',
  'ILIKE', 'BETWEEN', 'HAVING', 'DESC', 'ASC', 'DISTINCT', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
  'UNION', 'ALL', 'IS', 'NULL', 'OVER', 'PARTITION BY', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX',
]

// Las de varias palabras van primero para que el regex no las corte a la mitad.
const PATRON = new RegExp(
  `\\b(${[...PALABRAS_CLAVE].sort((a, b) => b.length - a.length).join('|')})\\b`,
  'gi',
)

/** Resalta las palabras clave de `sql` con `<span>` coloreados; suficiente para que la consulta
 * se lea de un vistazo sin traer una librería de resaltado completa. */
export function resaltarSql(sql: string): ReactNode {
  const partes = sql.split(PATRON)
  return partes.map((parte, indice) =>
    PALABRAS_CLAVE.includes(parte.toUpperCase()) ? (
      <span key={indice} className="font-semibold text-primary">
        {parte}
      </span>
    ) : (
      <span key={indice}>{parte}</span>
    ),
  )
}

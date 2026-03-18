
# Reglas de Negocio para Registro Financiero
1. **Ingresos vs Gastos**: 
   - Si el usuario indica que "recibió dinero", se debe registrar como un `ingreso` (saldo a favor).
   - Si el usuario indica que "registre un gasto" o que "utilizó dinero", se debe registrar como un `gasto`.
2. **Métodos de Pago**:
   - Para cada gasto, es obligatorio identificar si se pagó con "efectivo" (dinero físico/transferencia directa) o con "tarjeta" (tarjeta de crédito).
   - Si el usuario no especifica el método de pago al registrar un gasto, asume "efectivo" o pregúntale para confirmar, según el contexto.
3. **Saldos Mensuales**:
   - Al solicitar un resumen o saldo mensual, calcula la diferencia entre los ingresos y los gastos del mes correspondiente.
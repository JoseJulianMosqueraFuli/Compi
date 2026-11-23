# Compi para iPhone

El iPhone importa cambios desde Salud cuando pulsas **Sincronizar ahora** con la app abierta. En Salud puedes elegir qué historial comparten Huawei Health y las demás fuentes. Compi solicita lectura de entrenamientos, sueño, frecuencia cardiaca y peso corporal según tus selecciones. Elige las categorías en Compi y concede acceso en la pantalla del sistema. Un resultado vacío también puede indicar acceso limitado.

## Conectar el equipo

1. Prepara la base de datos y el receptor local según el [README del proyecto](../README.md). El receptor escucha por HTTPS. Usa un certificado con el nombre de tu Mac en el SAN y una autoridad en la que confíe el iPhone. Conserva la clave privada del servidor en el Mac.
2. Abre `Compi.xcodeproj` en Xcode 16 o posterior, elige un equipo de firma con HealthKit y configura tu identificador de aplicación. Selecciona el iPhone como destino y ejecuta **Compi**. El proyecto tiene iOS 17 como versión mínima.
3. Conecta ambos equipos a la misma Wi-Fi. En Compi escribe la dirección del receptor, por ejemplo `https://mi-mac.local:8443`, y el valor de `HEALTHKIT_SYNC_TOKEN` del backend. Pulsa **Guardar conexión**. La app acepta nombres `.local`, IPv4 privadas y direcciones IPv6 locales únicas. Mantén la misma dirección para reconectar con la misma base.
4. Selecciona las categorías, pulsa **Sincronizar ahora** y permite el acceso a la red local. El historial inicial puede requerir varios lotes. Las siguientes sincronizaciones continúan desde el último lote confirmado.

## Cuando se interrumpe el envío

La app prepara una página por categoría en archivos protegidos al bloquear el dispositivo y excluidos de copias de seguridad. Conserva el lote y el ancla siguiente juntos hasta que el servidor confirma la secuencia. En el siguiente intento reenvía el mismo contenido, incluso si el backend ya había terminado antes del corte. El historial que aún no se ha paginado permanece en Salud. Los cambios incluyen eliminaciones y el identificador de la aplicación que escribió cada muestra. Desactivar una categoría detiene sus envíos.

Las credenciales se guardan en el llavero del dispositivo. Renovar el token para la misma dirección conserva la secuencia. Cada base admite un solo iPhone por categoría en esta versión. Un conflicto de secuencia retiene el lote para revisar el destino o recuperar la base correcta. Reinstalar la app elimina sus archivos de sincronización.

## Restablecer una categoría

Desactivar una categoría pausa sus envíos y conserva el historial importado. Para borrar su posición local y el lote pendiente, selecciona **Recuperación → Reiniciar una categoría** y confirma el nombre. La app desactiva esa categoría y mantiene los datos originales en Salud.

Si vas a reconstruir esa categoría desde Salud, deja la sincronización detenida. En el Mac, desde `backend/` y con su entorno Python activo, ejecuta `python -m app.reset_healthkit --kind workout --confirm` para entrenamientos. Este comando elimina en el receptor las observaciones y el cursor de la categoría elegida. Las demás categorías usan sus propios cursores. Para las otras categorías sustituye `workout` por `sleep`, `heart_rate` o `body_mass`. Activa otra vez la categoría en el iPhone y sincroniza. Solo se recuperará aquello que Salud todavía conserve y permita leer.

## Verificación con datos de prueba

Desde `ios/`, las comprobaciones reproducen un reintento tras perder una confirmación, una eliminación y un destino rechazado:

```sh
swiftc Compi/SyncData.swift Compi/Connection.swift Tests/SyncChecks.swift -o /tmp/compi-sync-checks
/tmp/compi-sync-checks
```

En un Mac con Xcode completo puedes compilar la app sin firma:

```sh
xcodebuild -project Compi.xcodeproj -scheme Compi -configuration Debug \
  -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

Para validar el reloj, compara en Salud la aplicación de origen de un entrenamiento con la procedencia recibida en el Mac. Repite la sincronización y verifica que el panel mantiene la misma cantidad de sesiones. [Consultas incrementales de HealthKit](https://developer.apple.com/documentation/healthkit/executing-anchored-object-queries) · [Permisos de Salud](https://developer.apple.com/documentation/healthkit/authorizing-access-to-health-data)

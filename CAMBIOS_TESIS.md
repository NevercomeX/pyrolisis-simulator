# Cambios al simulador (para la tesina)

1. Propiedades del aceite: se deshabilitaron las correlaciones sin fuente (PCS, viscosidad, °API, BS&W).
   La GUI y los informes PDF/Word ahora indican "requiere ensayo de laboratorio".
2. Conclusiones automáticas de los informes: se quitaron afirmaciones no demostradas
   (autosuficiencia "garantizada", "valida la precisión", "alto valor agregado").
3. Pérdidas de calor de la carcasa: ahora se cuentan también en modo de rampa manual.
   Nuevo parámetro T_ambient_C (30 °C por defecto) y salida shell_loss_kwh.
4. Eficiencia del quemador por defecto: 85 % (antes 70 %), igual que en la tesina.
5. Terminología: "Bio-Crudo/Bio-Oil/Bio-Char" → aceite pirolítico / char.
6. Perfiles: selector en la barra lateral ("General" y "Caso de estudio: corrida PROENERGÉTICOS").
   El perfil de tesis carga todos los datos de la corrida; botón para restablecerlos.
   CLI: `python cli.py --perfil tesis`. Origen de cada valor en pyrolysis/profiles.py.
   Nuevo parámetro de materia prima: temperatura de inicio de pirólisis (370 °C en la tesis).
7. Nuevo script corrida_tesis.py: corrida a 370 °C calibrada, tabla de entradas con su origen,
   sensibilidad (h_eff ±25/50 %, sostenimiento 90/150 min) y figuras coherentes.

Aplicar: `git apply cambios_simulador.patch` en la raíz del repositorio.
Las 13 pruebas pasan (`python -m unittest tests.test_simulation`).

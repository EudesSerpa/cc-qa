# cc-qa

Plugin personal de Claude Code con el comando `/cc-qa:qa`: QA adversarial sobre un diff.

Los agentes que escriben el código nunca lo juzgan. Cada agente de QA arranca con contexto limpio,
ve solo el diff, la especificación y el código, e intenta romperlo. Un juez reproduce cada hallazgo
y deja un test rojo por bug confirmado. No corrige código ni hace commit.

| Agente                    | Técnica                                                                          |
| ------------------------- | -------------------------------------------------------------------------------- |
| `qa-adversarial-reviewer` | Revisión con un enfoque: dinero, concurrencia, seguridad, tenancy o corrección   |
| `qa-mutation-tester`      | Mutación acotada (StrykerJS, mutmut, ...) y tests que matan los mutantes reales  |
| `qa-property-tester`      | Propiedades derivadas de la especificación (fast-check, Hypothesis, ...)         |
| `qa-api-fuzzer`           | Fuzzing de endpoints y matriz de acceso (sin token, sin permiso, otro tenant)    |
| `qa-ai-redteam`           | Respuestas hostiles del modelo en un pipeline con LLM                             |
| `qa-judge`                | Reproduce cada hallazgo; deja un test rojo por bug aceptado                       |

## Instalar

```text
/plugin marketplace add EudesSerpa/cc-qa
/plugin install cc-qa@cc-qa
```

El repo es privado: la máquina necesita acceso de lectura a GitHub con esta cuenta (`gh auth login`
o el gestor de credenciales de Git). Para actualizar después de un push:

```text
/plugin marketplace update cc-qa
```

Para probar cambios sin hacer push, agrega la carpeta local como marketplace:
`/plugin marketplace add C:/Dev/personal/cc-qa`.

## Uso

| Comando                   | Qué revisa                                                                                    |
| ------------------------- | --------------------------------------------------------------------------------------------- |
| `/cc-qa:qa`               | Igual que `/cc-qa:qa <rama base>` (la rama base sale de la configuración del proyecto)        |
| `/cc-qa:qa <rama>`        | Lo que tendría un PR de la rama actual hacia `<rama>`, más los cambios sin commit              |
| `/cc-qa:qa diff`          | Solo los cambios sin commit (staged, unstaged y archivos nuevos)                               |
| `/cc-qa:qa setup`         | Crea o actualiza la configuración de QA del proyecto                                           |

Opciones: `--paths <archivo>...`, `--deep`, `--review`, `--only mutation|property|fuzz|redteam|review`.

## Configuración por proyecto

El plugin es genérico. Lo específico de cada proyecto vive en el repo, sin entrar a Git:

| Archivo                       | Contenido                                                                          |
| ----------------------------- | ---------------------------------------------------------------------------------- |
| `.claude/qa/project.md`       | Stacks, comandos, bases de prueba aisladas, contrato de la API, reglas del proyecto |
| `.claude/qa/routing.md`       | Qué técnicas corren según la ruta del archivo cambiado                             |
| Configs y scripts de las herramientas | Adaptados de `plugins/cc-qa/skills/qa/templates/`                           |

La primera vez que corres `/cc-qa:qa` en un proyecto sin `.claude/qa/`, el comando inspecciona el
repo, propone la configuración y las herramientas, y espera tu aprobación antes de escribir nada
([setup.md](plugins/cc-qa/skills/qa/setup.md)). Todo lo que crea queda en `.git/info/exclude` y
las herramientas se instalan sin tocar manifiestos ni lockfiles (`bun add --no-save`,
`uv run --with`, un makefile personal junto al del equipo).

Los tests que importan una herramienta que el proyecto no declara (por ejemplo `fast-check` o
`hypothesis`) no se pueden subir hasta que el equipo la adopte. El reporte los marca.

## Estructura

```text
.claude-plugin/marketplace.json     marketplace personal
plugins/cc-qa/
  .claude-plugin/plugin.json
  skills/qa/SKILL.md                flujo: alcance, ruteo, preflight, agentes, juez, reporte
  skills/qa/setup.md                cómo configurar un proyecto nuevo
  skills/qa/templates/              stryker.config.mjs, qa_mutation.py, qa.mk
  agents/qa-*.md                    los seis agentes
```

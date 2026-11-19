# Lecturas para mejorar odd-ws

Lista de fuentes verificadas el 2026-11-18. Cada una se encontró en la página de su editor original, o en una búsqueda que la muestra en ese dominio. Las fuentes que otro asistente citó y no existen con ese título quedaron fuera. Al estudiar una idea, se le pasa a la sesión la lectura que la alimenta.

Cada fila nombra la idea del [roadmap](../roadmap.md#ideas) o el problema que alimenta:

- **I17:** la calidad de la revisión.
- **I22:** las reglas que cambian.
- **I28:** el costo de revisar.
- **I47:** los chequeos antes de los revisores.
- **multi-host:** el núcleo común.

## Por dónde empezar

| Lectura | Autor y fecha | Para qué sirve |
|---|---|---|
| [Harness engineering for coding agent users](https://martinfowler.com/articles/harness-engineering.html) | Birgitta Böckeler, martinfowler.com, abril de 2026 | Divide el arnés en guías, que actúan antes de que el agente actúe, y sensores, que actúan después. Separa también los chequeos computacionales de los inferenciales, y los baratos van primero. Da el vocabulario para decidir a dónde gradúa cada regla, y para I47. |
| [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps) | Prithvi Rajasekaran, Anthropic, marzo de 2026 | Separa el generador del evaluador, y vuelve escéptico al evaluador con ejemplos de puntajes desglosados (I17). Para la ansiedad de contexto, compactar no alcanzó y sirvió reiniciar el contexto con un traspaso estructurado. |
| [Using LLM-as-a-Judge For Evaluation: A Complete Guide](https://hamel.dev/blog/posts/llm-judge/) | Hamel Husain, octubre de 2024, actualizada en 2026 | Calibra al juez contra las críticas de un experto, con un veredicto de aprobado o rechazado. Mide por separado los aciertos y las falsas alarmas, porque el acuerdo bruto engaña. Es lo que hace `eval-reviewers`, afinado (I17). |
| [ReviewBench: An open benchmark for AI code review](https://github.blog/ai-and-ml/github-copilot/reviewbench-an-open-benchmark-for-ai-code-review/) | GitHub, octubre de 2026 | Precisión, recall y Fβ para medir el rendimiento de una revisión, ponderando el ruido contra la cobertura (I28). |
| [Replacing Judges with Juries](https://arxiv.org/abs/2404.18796) | Verga y otros, Cohere, abril de 2024 | Un panel de jueces distintos rinde más que un juez grande, con menos sesgo y menor costo. Respalda las lentes distintas en vez de la misma mirada tres veces (I17). |
| [Stale Instruction Files Override the Code in Coding Agents: A One-Sentence Fix](https://arxiv.org/abs/2610.30571) | Xiaonan Xu y Wenjing Wu, octubre de 2026 | Los agentes siguieron un archivo de instrucciones viejo en el 90,1% de las elecciones. Una oración de precedencia llevó al 91,4% las que siguieron al código. Pone en duda la propuesta de la pregunta 5 del [estudio de I22](reglas-que-cambian.md), según la cual la regla gana sobre el hermano vigente. |

## Para I22: las reglas que cambian

| Lectura | Autor y fecha | Para qué sirve |
|---|---|---|
| [Rule Deprecation](https://eslint.org/docs/latest/extend/rule-deprecation) | Documentación de ESLint | Un esquema probado para retirar una regla: `replacedBy`, `deprecatedSince` y `availableUntil`. |
| [Why Does CLAUDE.md Keep Growing? Catastrophic Remembering in Agentic Coding](https://arxiv.org/abs/2608.11095) | Kushal Chakrabarti, agosto de 2026 | Las reglas se acumulan porque se pierde su porqué; guardarlo permitió podar el archivo. Respalda la evidencia de cada fila de la matriz, y el aviso de tamaño por capa. |
| [Context Rot in AI-Assisted Software Development](https://arxiv.org/abs/2606.09090) | Christoph Treude y Sebastian Baltes, junio de 2026 | Los chequeos de consistencia de la documentación encontraron referencias viejas en el 23% de 356 repos. Es un detector determinista de reglas desactualizadas. |
| [ArchUnit: Freezing Arch Rules](https://www.archunit.org/userguide/html/000_Index.html) (sección 8.6) | TNG, ArchUnit | Guarda las violaciones que ya existen, para que solo fallen las nuevas. Es la versión de ArchUnit de lo que hace `filtrar_preexistentes`. |
| [Agentic Fitness Functions](https://www.infoq.com/articles/agentic-fitness-functions-evolutionary-architecture/) | Mahato, Sieczkowski y Kuppusamy, InfoQ, agosto de 2026 | Rúbricas versionadas como código, calibradas contra decisiones humanas anteriores, y un monitor de deriva de los ADR. Es lo publicado más parecido a odd-ws. |

## Para los chequeos deterministas (I47)

| Lectura | Autor y fecha | Para qué sirve |
|---|---|---|
| [Building Evolutionary Architectures](https://www.oreilly.com/library/view/building-evolutionary-architectures/9781492097532/ch04.html), capítulo 4 | Ford, Parsons, Kua y Sadalage, O'Reilly, 2.ª edición, 2022 | La fuente de las fitness functions como gobierno automático de la arquitectura. |
| [Testing rules](https://docs.semgrep.dev/writing-rules/testing-rules) | Documentación de Semgrep | Las anotaciones `ruleid` y `ok`, y `semgrep --test`. Sirven de modelo para que cada regla graduada traiga un caso que la rompe y otro que la cumple. |

## Para el núcleo común (multi-host)

| Lectura | Autor y fecha | Para qué sirve |
|---|---|---|
| [Agent Skills](https://agentskills.io/) | Estándar abierto que inició Anthropic | El formato `SKILL.md` portable, que se carga por partes. |
| [Unlocking the Codex harness: how we built the App Server](https://openai.com/index/unlocking-the-codex-harness/) | Celia Chen, OpenAI, febrero de 2026 | Un núcleo del arnés expuesto a varias superficies por una API JSON-RPC. Es un diseño de referencia para los adaptadores finos. |
| [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/) | OpenAI, febrero de 2026 | Revisión de agente a agente, y documentación que se mantiene honesta con linters y CI. |
| [Advanced Context Engineering for Coding Agents](https://humanlayer.dev/blog/advanced-context-engineering) | Dex Horthy, HumanLayer, agosto de 2025 | Compactación intencional y frecuente, y traspasos entre investigar, planear e implementar como artefactos estructurados. |

## En español

No hay contenido original en español al nivel de las fuentes en inglés. Lo único sólido:

- [Mejores prácticas para Claude Code](https://code.claude.com/docs/es/best-practices), la documentación oficial traducida;
- [Qué es el AI harness y el harness engineering](https://www.webreactiva.com/blog/ai-harness), de Web Reactiva: una introducción que cita fuentes primarias.

## Verificadas pero fuera de las tablas

- Eugene Yan, «Evaluating the Effectiveness of LLM-Evaluators» (agosto de 2024).
- Panickssery, Bowman y Feng, «LLM Evaluators Recognize and Favor Their Own Generations» (arXiv 2404.13076).
- Gloaguen y otros, «Evaluating AGENTS.md» (arXiv 2602.11988). Los archivos de contexto no ayudaron y costaron más del 20% extra.
- Mitchell Hashimoto, «My AI Adoption Journey» (febrero de 2026).
- Anthropic, «Effective context engineering for AI agents» (septiembre de 2025) y «Effective harnesses for long-running agents» (noviembre de 2025).

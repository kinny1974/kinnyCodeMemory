/**
 * OpenCode Plugin for KinnyCode Memory Server
 *
 * This plugin provides direct integration with the KinnyCode Memory Server
 * without requiring the Python MCP wrapper.
 */

import { tool, type Plugin } from "@opencode-ai/plugin";
import { z } from "zod";

// ── Configuration ──────────────────────────────────────────────────
const DEFAULT_SERVER_URL = "http://127.0.0.1:8007";
const DEFAULT_PROJECT_ID = "default";

// ── HTTP Client ────────────────────────────────────────────────────
async function httpRequest(
  url: string,
  options: RequestInit = {}
): Promise<any> {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`HTTP ${response.status}: ${error}`);
  }

  return response.json();
}

// ── Plugin Definition ──────────────────────────────────────────────
export const KinnyCodeMemoryPlugin: Plugin = async (ctx, options) => {
  // Get server URL from options or environment
  const serverUrl =
    (options?.serverUrl as string) ||
    process.env.KINNYCODE_SERVER_URL ||
    DEFAULT_SERVER_URL;

  // Get project ID from options or environment
  const projectId =
    (options?.projectId as string) ||
    process.env.KINNYCODE_PROJECT_ID ||
    DEFAULT_PROJECT_ID;

  const baseUrl = serverUrl.replace(/\/$/, "");

  return {
    // ── Tool Definitions ──────────────────────────────────────────
    tool: {
      // ── 1. Index a code file ──────────────────────────────────
      indexar_archivo: tool({
        description: (
          "Indexa un archivo de código fuente en la base de conocimiento "
          + "RAG (Capa 3 — memoria a largo plazo). El contenido se divide "
          + "en fragmentos (chunks) y se generan embeddings para búsqueda "
          + "semántica posterior."
        ),
        args: {
          file_path: tool.schema.string().describe("Ruta del archivo de código a indexar"),
          content: tool.schema.string().describe("Contenido completo del archivo de código fuente"),
          language: tool.schema.string().describe("Lenguaje de programación del archivo (ej: 'python', 'javascript')"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/index-file`, {
            method: "POST",
            body: JSON.stringify({
              file_path: args.file_path,
              content: args.content,
              language: args.language,
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 2. Batch project indexing ──────────────────────────────
      indexar_proyecto: tool({
        description: (
          "Indexa múltiples archivos de código en lote dentro de la base "
          + "de conocimiento RAG. Opcionalmente, limpia todo el codebase "
          + "antes de indexar para empezar desde cero."
        ),
        args: {
          file_paths: tool.schema.array(tool.schema.string()).describe("Lista de rutas de archivos a indexar"),
          clean_first: tool.schema.boolean().optional().describe("Limpiar codebase antes de indexar"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/index-file-paths`, {
            method: "POST",
            body: JSON.stringify({
              file_paths: args.file_paths,
              project_id: projectId,
              clean_first: args.clean_first || false,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 3. Semantic code search ────────────────────────────────
      buscar_codigo: tool({
        description: (
          "Realiza una búsqueda semántica en el codebase indexado. "
          + "Encuentra fragmentos de código relevantes basados en el "
          + "significado semántico, no solo coincidencias de texto."
        ),
        args: {
          prompt: tool.schema.string().describe("Consulta de búsqueda en lenguaje natural"),
          n_results: tool.schema.number().optional().describe("Número de resultados a retornar (default: 5)"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/semantic-search`, {
            method: "POST",
            body: JSON.stringify({
              prompt: args.prompt,
              project_id: projectId,
              n_results: args.n_results || 5,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 4. Retrieve RAG context ───────────────────────────────
      recuperar_contexto: tool({
        description: (
          "Recupera contexto completo de las 5 capas de memoria: "
          + "L1 (trabajo), L2 (corto plazo), L3 (código), L4 (documentos), "
          + "L5 (tareas). Útil para obtener todo el contexto relevante."
        ),
        args: {
          prompt: tool.schema.string().describe("Consulta para recuperar contexto"),
          layers: tool.schema.array(tool.schema.string()).optional().describe("Capas a consultar (code, documents, conversations, decisions, tasks)"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/retrieve-context`, {
            method: "POST",
            body: JSON.stringify({
              prompt: args.prompt,
              project_id: projectId,
              layers: args.layers || ["code", "documents", "conversations", "decisions", "tasks"],
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 5. Index document ──────────────────────────────────────
      indexar_documento: tool({
        description: (
          "Indexa un documento (PDF, Markdown, TXT) en la base de "
          + "conocimiento RAG (Capa 4 — documentos). El contenido se "
          + "divide en chunks y se generan embeddings."
        ),
        args: {
          file_path: tool.schema.string().describe("Ruta del documento a indexar"),
          content: tool.schema.string().optional().describe("Contenido del documento (opcional si file_path es válido)"),
          doc_type: tool.schema.string().optional().describe("Tipo de documento (pdf, markdown, text)"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/index-document`, {
            method: "POST",
            body: JSON.stringify({
              file_path: args.file_path,
              content: args.content,
              doc_type: args.doc_type,
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 6. Search documents ────────────────────────────────────
      buscar_documentos: tool({
        description: (
          "Busca en documentos indexados (PDF, MD, TXT) usando "
          + "búsqueda semántica. Útil para encontrar información "
          + "en documentación, manuales, etc."
        ),
        args: {
          query: tool.schema.string().describe("Consulta de búsqueda"),
          n_results: tool.schema.number().optional().describe("Número de resultados a retornar"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/search-documents`, {
            method: "POST",
            body: JSON.stringify({
              query: args.query,
              project_id: projectId,
              n_results: args.n_results || 5,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 7. List documents ──────────────────────────────────────
      listar_documentos: tool({
        description: "Lista todos los documentos indexados en el proyecto actual.",
        args: {},
        async execute() {
          const result = await httpRequest(
            `${baseUrl}/list-documents?project_id=${projectId}`
          );
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 8. Save conversation ───────────────────────────────────
      guardar_conversacion: tool({
        description: (
          "Guarda una conversación en la capa de memoria de corto "
          + "plazo (L2). Permite recuperar el historial de conversaciones "
          + "anteriores."
        ),
        args: {
          session_id: tool.schema.string().describe("ID de la sesión de conversación"),
          messages: tool.schema.array(
            tool.schema.object({
              role: tool.schema.string().describe("Rol del mensaje (user, assistant)"),
              content: tool.schema.string().describe("Contenido del mensaje"),
            })
          ).describe("Lista de mensajes de la conversación"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/save-conversation`, {
            method: "POST",
            body: JSON.stringify({
              session_id: args.session_id,
              messages: args.messages,
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 9. Load conversation ───────────────────────────────────
      cargar_conversacion: tool({
        description: "Carga el historial de una conversación guardada.",
        args: {
          session_id: tool.schema.string().describe("ID de la sesión a cargar"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/load-conversation`, {
            method: "POST",
            body: JSON.stringify({
              session_id: args.session_id,
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 10. Remember decision ──────────────────────────────────
      guardar_decision: tool({
        description: (
          "Guarda una decisión técnica en la capa de memoria de "
          + "arquitectura (L2). Permite registrar y recuperar "
          + "decisiones de diseño."
        ),
        args: {
          decision: tool.schema.string().describe("Decisión técnica a guardar"),
          context: tool.schema.string().describe("Contexto y justificación de la decisión"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/remember-decision`, {
            method: "POST",
            body: JSON.stringify({
              key_decision: args.decision,
              context: args.context,
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 11. Project info ───────────────────────────────────────
      info_proyecto: tool({
        description: "Muestra estadísticas e información del proyecto actual.",
        args: {},
        async execute() {
          const result = await httpRequest(`${baseUrl}/project-info`, {
            method: "POST",
            body: JSON.stringify({
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 12. Re-index file ──────────────────────────────────────
      reindexar_archivo: tool({
        description: (
          "Re-indexa un archivo de código si su contenido ha cambiado. "
          + "El servidor verifica automáticamente si el hash del archivo "
          + "es diferente al almacenado."
        ),
        args: {
          file_path: tool.schema.string().describe("Ruta del archivo a re-indexar"),
          content: tool.schema.string().describe("Contenido actualizado del archivo"),
          language: tool.schema.string().describe("Lenguaje de programación"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/reindex-file`, {
            method: "POST",
            body: JSON.stringify({
              file_path: args.file_path,
              content: args.content,
              language: args.language,
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 13. Delete document ────────────────────────────────────
      eliminar_documento: tool({
        description: (
          "Elimina un documento previamente indexado de la capa L4. "
          + "Útil cuando un documento ya no es relevante o fue indexado "
          + "por error."
        ),
        args: {
          document_id: tool.schema.string().describe("ID del documento a eliminar"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/delete-document`, {
            method: "DELETE",
            body: JSON.stringify({
              document_id: args.document_id,
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 14. Save task ──────────────────────────────────────────
      guardar_tarea: tool({
        description: (
          "Crea o actualiza una tarea en la capa L5 (memoria de tareas). "
          + "Las tareas se pueden buscar semánticamente y tienen estado, "
          + "prioridad y dependencias."
        ),
        args: {
          task_id: tool.schema.string().optional().describe("ID de la tarea (opcional para nueva tarea)"),
          title: tool.schema.string().describe("Título de la tarea"),
          description: tool.schema.string().describe("Descripción detallada de la tarea"),
          status: tool.schema.string().describe("Estado de la tarea (pending, in_progress, completed, blocked)"),
          priority: tool.schema.string().describe("Prioridad (low, medium, high, critical)"),
          dependencies: tool.schema.array(tool.schema.string()).optional().describe("IDs de tareas dependientes"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/tasks/upsert`, {
            method: "POST",
            body: JSON.stringify({
              task_id: args.task_id,
              title: args.title,
              description: args.description,
              status: args.status,
              priority: args.priority,
              dependencies: args.dependencies || [],
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 15. Search tasks ───────────────────────────────────────
      buscar_tareas: tool({
        description: (
          "Realiza una búsqueda semántica en las tareas indexadas. "
          + "Útil para encontrar tareas similares o relacionadas con "
          + "un tema específico."
        ),
        args: {
          query: tool.schema.string().describe("Consulta de búsqueda en lenguaje natural"),
          status: tool.schema.string().optional().describe("Filtrar por estado (pending, in_progress, completed, blocked)"),
          n_results: tool.schema.number().optional().describe("Número de resultados a retornar"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/tasks/search`, {
            method: "POST",
            body: JSON.stringify({
              query: args.query,
              status: args.status,
              n_results: args.n_results || 10,
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 16. Consolidate memory ─────────────────────────────────
      consolidar_memoria: tool({
        description: (
          "Consolida la memoria de largo plazo, eliminando datos "
          + "obsoletos y fusionando información redundante. "
          + "Útil para mantener la base de conocimiento limpia."
        ),
        args: {},
        async execute() {
          const result = await httpRequest(`${baseUrl}/consolidate`, {
            method: "POST",
            body: JSON.stringify({
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 17. Session context ────────────────────────────────────
      contexto_sesion: tool({
        description: (
          "Genera contexto proactivo basado en la sesión actual. "
          + "Analiza el historial reciente y sugiere información "
          + "relevante para continuar el trabajo."
        ),
        args: {
          recent_messages: tool.schema.array(
            tool.schema.object({
              role: tool.schema.string().describe("Rol del mensaje"),
              content: tool.schema.string().describe("Contenido del mensaje"),
            })
          ).optional().describe("Mensajes recientes de la sesión"),
        },
        async execute(args) {
          const result = await httpRequest(`${baseUrl}/session-context`, {
            method: "POST",
            body: JSON.stringify({
              project_id: projectId,
              recent_messages: args.recent_messages || [],
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),

      // ── 18. Clear project ──────────────────────────────────────
      limpiar_proyecto: tool({
        description: (
          "Elimina todos los datos indexados de un proyecto. "
          + "⚠️ OPERACIÓN DESTRUCTIVA: No se puede deshacer. "
          + "Útil para empezar desde cero con un proyecto."
        ),
        args: {
          confirm: tool.schema.boolean().describe("Confirmar limpieza (debe ser true para ejecutar)"),
        },
        async execute(args) {
          if (!args.confirm) {
            return "❌ Operación cancelada. Establece confirm=true para eliminar todos los datos del proyecto.";
          }
          const result = await httpRequest(`${baseUrl}/clear-project`, {
            method: "POST",
            body: JSON.stringify({
              project_id: projectId,
            }),
          });
          return JSON.stringify(result, null, 2);
        },
      }),
    },
  };
};

// ── Plugin Export ──────────────────────────────────────────────────
export default KinnyCodeMemoryPlugin;

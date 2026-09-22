/**
 * Ephemeral navigation intent from temporary local-model chat to Agent setup.
 * It deliberately never becomes a route, URL parameter, or stored record.
 */
export type AgentChatSetupIntent = {
  requestId: number;
  modelAlias: string | null;
};

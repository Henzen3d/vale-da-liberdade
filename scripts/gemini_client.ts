import * as fs from 'fs';
import * as path from 'path';

// Padrões de limites por categoria
const DEFAULT_LIMITS = {
  flash: { rpm: 15, rpd: 1000, tpm: 30000 },
  lite: { rpm: 15, rpd: 1500, tpm: 35000 },
  tts: { rpm: 10, rpd: 1000, tpm: 35000 }
};

interface UsageRecord {
  requests: number[];
  tokens: { timestamp: number; tokens: number }[];
}

interface UsageDatabase {
  [modelName: string]: UsageRecord;
}

function getModelCategory(modelName: string): 'flash' | 'lite' | 'tts' {
  const modelLower = modelName.toLowerCase();
  if (modelLower.includes('tts')) return 'tts';
  if (modelLower.includes('lite')) return 'lite';
  return 'flash';
}

function estimateTokens(contents: any): number {
  if (typeof contents === 'string') {
    return Math.floor(contents.split(/\s+/).length * 1.5) + 50;
  } else if (Array.isArray(contents)) {
    let total = 0;
    for (const item of contents) {
      if (typeof item === 'string') {
        total += item.split(/\s+/).length * 1.5;
      } else if (item && typeof item === 'object' && typeof item.text === 'string') {
        total += item.text.split(/\s+/).length * 1.5;
      } else {
        total += 100;
      }
    }
    return Math.floor(total) + 50;
  }
  return 1000;
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Funções concorrente-seguras com retry para Windows
function loadUsage(filePath: string): UsageDatabase {
  for (let i = 0; i < 30; i++) {
    try {
      if (!fs.existsSync(filePath)) {
        return {};
      }
      const raw = fs.readFileSync(filePath, 'utf-8');
      return JSON.parse(raw);
    } catch (e) {
      // Dorme entre 20ms e 120ms
      const sleepTime = 20 + Math.random() * 100;
      const start = Date.now();
      while (Date.now() - start < sleepTime) {} // Sincrono curto
    }
  }
  return {};
}

function saveUsage(filePath: string, data: UsageDatabase): void {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  for (let i = 0; i < 30; i++) {
    try {
      const tempPath = filePath + '.tmp';
      fs.writeFileSync(tempPath, JSON.stringify(data, null, 2), 'utf-8');
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
      }
      fs.renameSync(tempPath, filePath);
      return;
    } catch (e) {
      const sleepTime = 20 + Math.random() * 100;
      const start = Date.now();
      while (Date.now() - start < sleepTime) {}
    }
  }
  throw new Error(`Não foi possível persistir uso da API em ${filePath} devido a bloqueio.`);
}

export class GeminiClient {
  private client: any; // Instância real do GoogleGenAI
  private usageFile: string;
  private limits: typeof DEFAULT_LIMITS;

  constructor(apiKey?: string, usageFile?: string, originalSdkClient?: any) {
    // Inicializa o cliente real (espera-se que passe a instância do SDK se necessário)
    this.client = originalSdkClient;

    const projectRoot = path.resolve(__dirname, '..');
    this.usageFile = usageFile || path.join(projectRoot, 'sources', 'gemini_usage.json');

    // Carregar limites customizados
    this.limits = JSON.parse(JSON.stringify(DEFAULT_LIMITS)); // Deep clone
    for (const key of Object.keys(DEFAULT_LIMITS) as Array<keyof typeof DEFAULT_LIMITS>) {
      const prefix = `GEMINI_${key.toUpperCase()}_`;
      if (process.env[prefix + 'RPM']) this.limits[key].rpm = parseInt(process.env[prefix + 'RPM']!, 10);
      if (process.env[prefix + 'RPD']) this.limits[key].rpd = parseInt(process.env[prefix + 'RPD']!, 10);
      if (process.env[prefix + 'TPM']) this.limits[key].tpm = parseInt(process.env[prefix + 'TPM']!, 10);
    }
  }

  private getLimits(model: string) {
    const category = getModelCategory(model);
    return this.limits[category];
  }

  private async enforceRateLimit(model: string, estimatedTokens: number): Promise<void> {
    const limits = this.getLimits(model);
    const { rpm, rpd, tpm } = limits;

    while (true) {
      const now = Date.now();
      const nowS = now / 1000;
      const usage = loadUsage(this.usageFile);

      if (!usage[model]) {
        usage[model] = { requests: [], tokens: [] };
      }

      const modelData = usage[model];

      // Prune
      const requestsMinute = modelData.requests.filter(t => nowS - t < 60);
      const requestsDay = modelData.requests.filter(t => nowS - t < 86400);
      const tokensMinute = modelData.tokens.filter(entry => nowS - entry.timestamp < 60);

      modelData.requests = requestsDay;
      modelData.tokens = tokensMinute;

      // 1. RPD Limit
      if (requestsDay.length >= rpd) {
        throw new Error(`Daily limit reached (${rpd} requests/day) for model ${model}.`);
      }

      // 2. RPM Limit
      if (requestsMinute.length >= rpm) {
        const oldestReq = Math.min(...requestsMinute);
        const waitTimeMs = Math.max(100, (60 - (nowS - oldestReq)) * 1000 + 200);
        console.warn(`[gemini-client-ts] RPM limit reached for ${model}. Waiting ${waitTimeMs}ms...`);
        await delay(waitTimeMs);
        continue;
      }

      // 3. TPM Limit
      const currentTokens = tokensMinute.reduce((acc, val) => acc + val.tokens, 0);
      if (currentTokens + estimatedTokens >= tpm) {
        const oldestTokenTs = Math.min(...tokensMinute.map(e => e.timestamp));
        const waitTimeMs = Math.max(100, (60 - (nowS - oldestTokenTs)) * 1000 + 200);
        console.warn(`[gemini-client-ts] TPM limit reached for ${model}. Waiting ${waitTimeMs}ms...`);
        await delay(waitTimeMs);
        continue;
      }

      // Cota livre!
      modelData.requests.push(nowS);
      modelData.tokens.push({ timestamp: nowS, tokens: estimatedTokens });
      saveUsage(this.usageFile, usage);
      break;
    }
  }

  private updateActualTokens(model: string, requestTimeS: number, actualTokens: number): void {
    try {
      const usage = loadUsage(this.usageFile);
      const modelData = usage[model];
      if (modelData && modelData.tokens) {
        for (const entry of modelData.tokens) {
          if (Math.abs(entry.timestamp - requestTimeS) < 1.0) {
            entry.tokens = actualTokens;
            break;
          }
        }
        saveUsage(this.usageFile, usage);
      }
    } catch (e) {
      // Silent error
    }
  }

  /**
   * Executa a geração de conteúdo aplicando controle de cota e retentativa progressiva.
   * Espera-se que execute o método generateContent do SDK passado no construtor.
   */
  async generateContent(model: string, contents: any, config?: any, maxRetries = 5, ...args: any[]): Promise<any> {
    const estimatedTokens = estimateTokens(contents);
    await this.enforceRateLimit(model, estimatedTokens);

    const requestTimeS = Date.now() / 1000;
    const baseDelay = 2.0; // segundos
    let lastException: any = null;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        if (!this.client || typeof this.client.models?.generateContent !== 'function') {
          throw new Error('SDK Client original não fornecido ou inválido no construtor.');
        }

        const response = await this.client.models.generateContent({
          model,
          contents,
          config,
          ...args
        });

        // Tentar ler usage metadata
        const totalTokens = response?.usageMetadata?.totalTokenCount;
        if (totalTokens) {
          this.updateActualTokens(model, requestTimeS, totalTokens);
        }

        return response;
      } catch (exc: any) {
        lastException = exc;
        const errorMsg = String(exc).toLowerCase();

        const isTransient =
          errorMsg.includes('429') ||
          errorMsg.includes('too many requests') ||
          errorMsg.includes('rate limit') ||
          errorMsg.includes('resource exhausted') ||
          errorMsg.includes('503') ||
          errorMsg.includes('service unavailable') ||
          errorMsg.includes('quota');

        if (!isTransient) {
          throw exc;
        }

        if (attempt === maxRetries) {
          console.error(`[gemini-client-ts] Todas as ${maxRetries} tentativas falharam.`);
          throw exc;
        }

        const jitter = (Math.random() - 0.5); // ±0.5s
        const delayS = (baseDelay * Math.pow(2, attempt - 1)) + jitter;
        const finalDelayMs = Math.max(500, delayS * 1000);

        console.warn(
          `[gemini-client-ts] Rate limit/erro transiente na tentativa ${attempt}/${maxRetries} para ${model}: ${exc}. ` +
          `Aguardando ${finalDelayMs}ms antes de tentar novamente...`
        );
        await delay(finalDelayMs);
      }
    }

    if (lastException) throw lastException;
  }
}

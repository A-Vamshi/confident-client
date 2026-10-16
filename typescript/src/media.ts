import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";

import { MLLMImage } from "./common/types";

const IMAGE_MIME_TYPES: Record<string, string> = {
  ".avif": "image/avif",
  ".bmp": "image/bmp",
  ".gif": "image/gif",
  ".heic": "image/heic",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".tif": "image/tiff",
  ".tiff": "image/tiff",
  ".webp": "image/webp",
};

const BASE64 =
  /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;

const MARKER = /\[CONFIDENT:IMAGE:([^\]]+)\]/g;

const MAPPING_FIELD = "imagesMapping";

const REGISTRY = new Map<string, Media>();

function guessMimeType(filePath: string): string | undefined {
  return IMAGE_MIME_TYPES[path.extname(filePath).toLowerCase()];
}

function httpUrl(url: string): URL | undefined {
  try {
    const parsed = new URL(url);
    return ["http:", "https:"].includes(parsed.protocol) && parsed.host
      ? parsed
      : undefined;
  } catch {
    return undefined;
  }
}

interface MediaSource {
  url?: string;
  dataBase64?: string;
  mimeType?: string;
  filename?: string;
}

export class Media {
  readonly url?: string;
  readonly dataBase64?: string;
  readonly mimeType?: string;
  readonly filename?: string;
  private readonly key: string;

  private constructor({ url, dataBase64, mimeType, filename }: MediaSource) {
    if ((url === undefined) === (dataBase64 === undefined)) {
      throw new Error("A Media needs either a url or dataBase64.");
    }
    if (!(url || dataBase64)) {
      throw new Error("A Media can't be empty.");
    }
    if (mimeType !== undefined && !mimeType.startsWith("image/")) {
      throw new Error(`Only images are supported for now, got "${mimeType}".`);
    }
    if (dataBase64 !== undefined && mimeType === undefined) {
      throw new Error('A local Media needs a mimeType, such as "image/png".');
    }

    this.url = url;
    this.dataBase64 = dataBase64;
    this.mimeType = mimeType;
    this.filename = filename;
    this.key =
      url !== undefined
        ? url.replace(/]/g, "%5D")
        : randomUUID().replace(/-/g, "");
  }

  static fromUrl(url: string, mimeType?: string): Media {
    const parsed = httpUrl(url);
    if (!parsed) {
      throw new Error(
        `"${url}" is not an http(s) URL. Use Media.fromFile for a local file.`,
      );
    }
    return new Media({
      url,
      mimeType: mimeType ?? guessMimeType(parsed.pathname),
      filename: path.posix.basename(parsed.pathname) || undefined,
    });
  }

  static fromFile(filePath: string, mimeType?: string): Media {
    return new Media({
      dataBase64: fs.readFileSync(filePath).toString("base64"),
      mimeType: mimeType ?? guessMimeType(filePath),
      filename: path.basename(filePath),
    });
  }

  static fromBytes(data: Uint8Array, mimeType: string): Media {
    return new Media({
      dataBase64: Buffer.from(data).toString("base64"),
      mimeType,
    });
  }

  static fromBase64(dataBase64: string, mimeType: string): Media {
    if (!BASE64.test(dataBase64)) {
      throw new Error(
        'dataBase64 is not valid base64. Pass the encoded bytes alone, without a "data:" prefix.',
      );
    }
    return new Media({ dataBase64, mimeType });
  }

  get isLocal(): boolean {
    return this.dataBase64 !== undefined;
  }

  toString(): string {
    if (this.isLocal) REGISTRY.set(this.key, this);
    return `[CONFIDENT:IMAGE:${this.key}]`;
  }
}

function mediaFor(key: string): Media | undefined {
  return REGISTRY.get(key) ?? (httpUrl(key) ? Media.fromUrl(key) : undefined);
}

export function parseMultimodal(text: string): Array<string | Media> {
  const parts: Array<string | Media> = [];
  let last = 0;
  for (const match of text.matchAll(MARKER)) {
    const media = mediaFor(match[1]);
    if (!media) continue;
    if (match.index > last) parts.push(text.slice(last, match.index));
    parts.push(media);
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function imageFor(key: string, media: Media): MLLMImage {
  if (!media.isLocal) return { url: key, local: false };
  return {
    url: "",
    local: true,
    mimeType: media.mimeType,
    dataBase64: media.dataBase64,
    ...(media.filename ? { filename: media.filename } : {}),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function markerKeys(value: unknown, keys: Set<string>): void {
  if (typeof value === "string") {
    for (const match of value.matchAll(MARKER)) keys.add(match[1]);
  } else if (Array.isArray(value)) {
    for (const item of value) markerKeys(item, keys);
  } else if (isRecord(value)) {
    for (const [field, item] of Object.entries(value)) {
      if (field !== MAPPING_FIELD) markerKeys(item, keys);
    }
  }
}

function withImagesMapping(
  holder: Record<string, unknown>,
): Record<string, unknown> {
  const keys = new Set<string>();
  markerKeys(holder, keys);
  const mapping: Record<string, MLLMImage> = {};
  for (const key of keys) {
    const media = mediaFor(key);
    if (media) mapping[key] = imageFor(key, media);
  }
  if (Object.keys(mapping).length === 0) return holder;
  const supplied = holder[MAPPING_FIELD] as
    Record<string, MLLMImage> | undefined;
  return { ...holder, [MAPPING_FIELD]: { ...mapping, ...supplied } };
}

function attach(value: unknown, holderPath: string[]): unknown {
  if (holderPath.length === 0) {
    return isRecord(value) ? withImagesMapping(value) : value;
  }
  const [head, ...rest] = holderPath;
  if (head === "*") {
    return Array.isArray(value)
      ? value.map((item) => attach(item, rest))
      : value;
  }
  if (isRecord(value) && head in value) {
    return { ...value, [head]: attach(value[head], rest) };
  }
  return value;
}

export function attachImagesMappings(
  body: unknown,
  holders: string[],
): unknown {
  return holders.reduce(
    (current, holder) => attach(current, holder.split(".").slice(1)),
    body,
  );
}

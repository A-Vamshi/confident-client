import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import { ConfidentAI, Media, parseMultimodal } from "../src";
import { TurnRole } from "../src/common";
import { clearConfidentEnv, lastCall, mockData, resetAxios } from "./helpers";

jest.mock("axios");

const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const LOCAL_MARKER = /^\[CONFIDENT:IMAGE:[0-9a-f]{32}\]$/;
const MARKER_KEY = /\[CONFIDENT:IMAGE:([^\]]+)\]/;
const PNG_BASE64 = PNG.toString("base64");

function keyOf(text: string): string {
  return MARKER_KEY.exec(text)![1];
}

let directory: string;

beforeAll(() => {
  directory = fs.mkdtempSync(path.join(os.tmpdir(), "confident-media-"));
});

afterAll(() => {
  fs.rmSync(directory, { recursive: true, force: true });
});

function writeFile(name: string): string {
  const filePath = path.join(directory, name);
  fs.writeFileSync(filePath, PNG);
  return filePath;
}

describe("Media", () => {
  it("keeps the URL in the marker of URL media", () => {
    const media = Media.fromUrl("https://cdn.example.com/cat.png");

    expect(`${media}`).toBe(
      "[CONFIDENT:IMAGE:https://cdn.example.com/cat.png]",
    );
    expect(media.mimeType).toBe("image/png");
    expect(media.filename).toBe("cat.png");
    expect(media.isLocal).toBe(false);
  });

  it("escapes closing brackets in URLs", () => {
    const media = Media.fromUrl("https://example.com/a[1].png");

    expect(`${media}`).toBe("[CONFIDENT:IMAGE:https://example.com/a[1%5D.png]");
  });

  it("leaves the mime type unset for a URL without an extension", () => {
    expect(Media.fromUrl("https://example.com/image?id=3").mimeType).toBe(
      undefined,
    );
  });

  it.each(["cat.png", "file:///tmp/cat.png", "ftp://x/a"])(
    "rejects the non-http URL %s",
    (url) => {
      expect(() => Media.fromUrl(url)).toThrow(/not an http/);
    },
  );

  it("sends file media as base64", () => {
    const media = Media.fromFile(writeFile("cat.PNG"));

    expect(media.isLocal).toBe(true);
    expect(media.dataBase64).toBe(PNG.toString("base64"));
    expect(media.mimeType).toBe("image/png");
    expect(media.filename).toBe("cat.PNG");
    expect(media.url).toBe(undefined);
    expect(`${media}`).toMatch(LOCAL_MARKER);
    expect(`${media}`).toBe(String(media));
  });

  it("gives each local media its own marker", () => {
    const first = Media.fromBytes(PNG, "image/png");
    const second = Media.fromBytes(PNG, "image/png");

    expect(`${first}`).not.toBe(`${second}`);
  });

  it("needs a mime type it cannot guess from the file", () => {
    const filePath = writeFile("cat.raw");

    expect(() => Media.fromFile(filePath)).toThrow(/mimeType/);
    expect(Media.fromFile(filePath, "image/png").mimeType).toBe("image/png");
  });

  it("throws for a missing file", () => {
    expect(() => Media.fromFile(path.join(directory, "missing.png"))).toThrow(
      /ENOENT/,
    );
  });

  it("keeps the encoded bytes of base64 media", () => {
    const encoded = PNG.toString("base64");

    expect(Media.fromBase64(encoded, "image/png").dataBase64).toBe(encoded);
  });

  it("rejects data URIs as base64", () => {
    const dataUri = `data:image/png;base64,${PNG.toString("base64")}`;

    expect(() => Media.fromBase64(dataUri, "image/png")).toThrow(
      /not valid base64/,
    );
  });

  it("supports only images", () => {
    expect(() =>
      Media.fromBytes(Buffer.from("%PDF"), "application/pdf"),
    ).toThrow(/Only images/);
    expect(() =>
      Media.fromUrl("https://example.com/a", "application/pdf"),
    ).toThrow(/Only images/);
  });

  it("rejects empty media", () => {
    expect(() => Media.fromBytes(new Uint8Array(), "image/png")).toThrow(
      /empty/,
    );
  });
});

describe("images mappings", () => {
  const ORIGINAL_ENV = { ...process.env };
  let client: ConfidentAI;

  beforeEach(() => {
    resetAxios();
    clearConfidentEnv();
    mockData({ id: "<ID>" });
    client = new ConfidentAI({ projectApiKey: "confident_us_proj_testkey" });
  });

  afterAll(() => {
    process.env = ORIGINAL_ENV;
  });

  type Sent = Record<string, unknown> & {
    imagesMapping?: Record<string, unknown>;
  };

  function sentBody(): Sent {
    return lastCall().data as Sent;
  }

  function sentGoldens(): Sent[] {
    return sentBody().goldens as Sent[];
  }

  it("maps the local media of each golden", async () => {
    const goldens = Array.from({ length: 20 }, (_, i) => ({
      input: `Golden ${i}: ${Media.fromBytes(PNG, "image/png")}`,
    }));

    await client.datasets.push("screenshots", goldens);

    for (const golden of sentGoldens()) {
      expect(golden.imagesMapping).toEqual({
        [keyOf(golden.input as string)]: {
          url: "",
          local: true,
          mimeType: "image/png",
          dataBase64: PNG_BASE64,
        },
      });
    }
  });

  it("sends URL media by reference", async () => {
    const media = Media.fromUrl("https://cdn.example.com/cat.png");

    await client.datasets.push("screenshots", [
      { input: `${media} What is this?` },
    ]);

    expect(sentGoldens()[0].imagesMapping).toEqual({
      "https://cdn.example.com/cat.png": {
        url: "https://cdn.example.com/cat.png",
        local: false,
      },
    });
  });

  it("maps media in turns on the golden", async () => {
    const content = `What is in ${Media.fromFile(writeFile("cat.png"))}?`;

    await client.datasets.push("photos", [
      {
        scenario: "A user asks about a photo",
        turns: [{ role: TurnRole.USER, content }],
      },
    ]);

    const sent = sentGoldens()[0];
    expect((sent.turns as Sent[])[0].imagesMapping).toBe(undefined);
    expect(sent.imagesMapping?.[keyOf(content)]).toMatchObject({
      filename: "cat.png",
    });
  });

  it("sends goldens without media unchanged", async () => {
    await client.datasets.push("plain", [{ input: "Hello" }]);

    expect(sentGoldens()[0]).toEqual({ input: "Hello" });
  });

  it("leaves unknown markers to the server", async () => {
    await client.datasets.push("plain", [
      { input: "[CONFIDENT:IMAGE:0123abcd]" },
    ]);

    expect(sentGoldens()[0].imagesMapping).toBe(undefined);
  });

  it("lets a supplied images mapping win", async () => {
    const text = `${Media.fromBytes(PNG, "image/png")}`;
    const supplied = { url: "https://cdn.example.com/cat.png", local: false };

    await client.datasets.push("screenshots", [
      { input: text, imagesMapping: { [keyOf(text)]: supplied } },
    ]);

    expect(sentGoldens()[0].imagesMapping).toEqual({ [keyOf(text)]: supplied });
  });

  it("leaves the goldens untouched", async () => {
    const golden = { input: `${Media.fromBytes(PNG, "image/png")}` };

    await client.datasets.push("screenshots", [golden]);

    expect(golden).toEqual({ input: golden.input });
  });

  it("maps media on the body of a golden update", async () => {
    const text = `${Media.fromBytes(PNG, "image/png")}`;

    await client.datasets.updateGolden("<DATASET-ID>", "<GOLDEN-ID>", {
      input: text,
    });

    expect(sentBody().imagesMapping).toHaveProperty([keyOf(text)]);
  });

  it("maps media per test case when running evals", async () => {
    const text = `${Media.fromBytes(PNG, "image/png")}`;

    await client.evaluate.runEvals("Vision", [
      { input: text, actualOutput: "A cat" },
    ]);

    const testCase = (sentBody().testCases as Sent[])[0];
    expect(testCase.imagesMapping).toHaveProperty([keyOf(text)]);
  });
});

describe("parseMultimodal", () => {
  it("returns text and media", () => {
    const media = Media.fromBytes(PNG, "image/png");
    const pulled =
      "[CONFIDENT:IMAGE:https://bucket.example.com/dog.png?sig=abc]";

    const parts = parseMultimodal(`Compare ${media} with ${pulled}.`);

    expect(parts[0]).toBe("Compare ");
    expect(parts[1]).toBe(media);
    expect(parts[2]).toBe(" with ");
    expect((parts[3] as Media).url).toBe(
      "https://bucket.example.com/dog.png?sig=abc",
    );
    expect((parts[3] as Media).mimeType).toBe("image/png");
    expect(parts[4]).toBe(".");
  });

  it("keeps unknown markers as text", () => {
    const text = "Before [CONFIDENT:IMAGE:0123abcd] after";

    expect(parseMultimodal(text)).toEqual([text]);
  });
});

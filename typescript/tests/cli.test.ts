import { API_KEY_HEADER } from "../src/api";
import { main } from "../src/cli";
import {
  clearConfidentEnv,
  lastCall,
  mockData,
  mockRaw,
  mockedAxios,
  resetAxios,
} from "./helpers";

jest.mock("axios");

const PROJECT_KEY = "confident_us_proj_testkey";
const POLICY = { id: "<GOVERNANCE-POLICY-ID>", name: "EU AI Act" };

describe("confident-ai gate", () => {
  const ORIGINAL_ENV = { ...process.env };
  let log: jest.SpyInstance;
  let error: jest.SpyInstance;

  beforeEach(() => {
    resetAxios();
    clearConfidentEnv();
    process.env.CONFIDENT_PROJ_API_KEY = PROJECT_KEY;
    log = jest.spyOn(console, "log").mockImplementation(() => {});
    error = jest.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    log.mockRestore();
    error.mockRestore();
  });

  afterAll(() => {
    process.env = ORIGINAL_ENV;
  });

  it("exits 0 when the policy passes", async () => {
    mockData({ passed: true, governancePolicy: POLICY });

    expect(await main(["gate"])).toBe(0);
    expect(lastCall().method).toBe("POST");
    expect(lastCall().url).toMatch(/\/v2\/governance\/assess$/);
    expect(lastCall().headers[API_KEY_HEADER]).toBe(PROJECT_KEY);
    expect(log).toHaveBeenCalledWith(
      expect.stringContaining("passed against EU AI Act"),
    );
  });

  it("exits 1 when the policy fails", async () => {
    mockData({ passed: false, governancePolicy: POLICY });

    expect(await main(["gate"])).toBe(1);
    expect(log).toHaveBeenCalledWith(
      expect.stringContaining("failed against EU AI Act"),
    );
  });

  it("prints nothing with --quiet", async () => {
    mockData({ passed: false, governancePolicy: POLICY });

    expect(await main(["gate", "--quiet"])).toBe(1);
    expect(log).not.toHaveBeenCalled();
    expect(error).not.toHaveBeenCalled();
  });

  it("reports API errors", async () => {
    mockRaw({ success: false, error: "Project has no governance policy" }, 400);

    expect(await main(["gate"])).toBe(1);
    expect(error).toHaveBeenCalledWith(
      expect.stringContaining("Project has no governance policy"),
    );
  });

  it("needs a project API key", async () => {
    delete process.env.CONFIDENT_PROJ_API_KEY;
    process.env.CONFIDENT_ORG_API_KEY = "confident_us_org_testkey";

    expect(await main(["gate"])).toBe(1);
    expect(mockedAxios).not.toHaveBeenCalled();
    expect(error).toHaveBeenCalledWith(
      expect.stringContaining("CONFIDENT_PROJ_API_KEY"),
    );
  });

  it("rejects unknown commands and options", async () => {
    expect(await main([])).toBe(2);
    expect(await main(["deploy"])).toBe(2);
    expect(await main(["gate", "--force"])).toBe(2);
    expect(mockedAxios).not.toHaveBeenCalled();
  });

  it("prints help", async () => {
    expect(await main(["--help"])).toBe(0);
    expect(await main(["gate", "-h"])).toBe(0);
    expect(log).toHaveBeenCalledWith(
      expect.stringContaining("Usage: confident-ai gate"),
    );
  });
});

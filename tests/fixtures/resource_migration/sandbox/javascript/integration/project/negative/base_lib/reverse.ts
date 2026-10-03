import { run as forbiddenRun } from "../../nodes/math.ts";

export const forbiddenNode = typeof forbiddenRun === "function" ? 1 : 0;

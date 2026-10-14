import type {Request} from "./types";
export function value(request: Request): number {return request.value + 1;}

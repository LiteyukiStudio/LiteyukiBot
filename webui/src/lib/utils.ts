import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Resolves conditional class inputs and Tailwind utility conflicts.
 * @param inputs - Class values accepted by `clsx`.
 * @returns One normalized class-name string with later Tailwind utilities taking precedence.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

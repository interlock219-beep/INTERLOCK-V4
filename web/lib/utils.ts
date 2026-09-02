type ClassValue =
  | string
  | number
  | null
  | undefined
  | boolean
  | ClassDictionary
  | ClassValue[]

interface ClassDictionary {
  [id: string]: unknown
}

function flatten(inputs: ClassValue[]): string[] {
  const classes: string[] = []

  for (const input of inputs) {
    if (input == null || input === false) continue
    if (typeof input === "string") {
      if (input.trim()) classes.push(input)
    } else if (Array.isArray(input)) {
      classes.push(...flatten(input))
    } else if (typeof input === "object") {
      for (const key in input as ClassDictionary) {
        if (
          Object.prototype.hasOwnProperty.call(input, key) &&
          (input as ClassDictionary)[key]
        ) {
          classes.push(key)
        }
      }
    }
  }

  return classes
}

export function cn(...inputs: ClassValue[]): string {
  return Array.from(new Set(flatten(inputs))).join(" ")
}

export class Store<T> {
  private value: T
  private readonly listeners = new Set<() => void>()
  private readonly onSubscribe: () => void

  constructor(initial: T, onSubscribe: () => void = () => {}) {
    this.value = initial
    this.onSubscribe = onSubscribe
  }

  get = (): T => this.value

  set(value: T): void {
    this.value = value
    this.listeners.forEach((listener) => listener())
  }

  subscribe = (listener: () => void): (() => void) => {
    this.onSubscribe()
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }
}

export class Channel<T> {
  private readonly listeners = new Set<(value: T) => void>()
  private readonly onSubscribe: () => void

  constructor(onSubscribe: () => void = () => {}) {
    this.onSubscribe = onSubscribe
  }

  emit(value: T): void {
    this.listeners.forEach((listener) => listener(value))
  }

  listen = (listener: (value: T) => void): (() => void) => {
    this.onSubscribe()
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }
}

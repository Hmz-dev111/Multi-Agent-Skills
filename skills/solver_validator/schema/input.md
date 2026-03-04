type: object
required: [depot, capacity, customers]
properties:
  depot:
    type: object
    required: [x, y]
    properties:
      x: {type: number}
      y: {type: number}
  capacity:
    type: number
  customers:
    type: array
    items:
      type: object
      required: [id, x, y, demand, ready, due, service]
      properties:
        id: {type: integer}
        x: {type: number}
        y: {type: number}
        demand: {type: number}
        ready: {type: number}
        due: {type: number}
        service: {type: number}
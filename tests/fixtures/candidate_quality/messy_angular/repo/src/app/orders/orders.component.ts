import { OrdersService } from "./service";

export class OrdersComponent {
  rows = new OrdersService().loadOrders();
}

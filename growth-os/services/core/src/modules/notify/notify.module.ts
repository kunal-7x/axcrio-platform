import { Module } from '@nestjs/common';
import { NotifyController } from './notify.controller.js';
import { NotifyService } from './notify.service.js';

@Module({
  controllers: [NotifyController],
  providers: [NotifyService],
  exports: [NotifyService],
})
export class NotifyModule {}

import { Module } from '@nestjs/common';
import { FlagsController } from './flags.controller.js';
import { FlagsService } from './flags.service.js';

@Module({
  controllers: [FlagsController],
  providers: [FlagsService],
  exports: [FlagsService],
})
export class FlagsModule {}

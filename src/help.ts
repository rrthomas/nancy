import Help from '@oclif/plugin-help'
import {Command} from '@oclif/config'

export default class NancyHelp extends Help {
  public showCommandHelp(command: Command) {
    super.showCommandHelp(command)
    console.log('Use `-\' as a file name to indicate standard input or output')
  }
}
